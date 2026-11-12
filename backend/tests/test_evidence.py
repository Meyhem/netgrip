from datetime import UTC, datetime

import pytest

from netgrip.adapters.fakes import FakeModelClient
from netgrip.boundary.events import EventDraft
from netgrip.engine.budget import CallContext
from netgrip.evidence.service import EvidenceService
from netgrip.evidence.status import Source, claim_status
from netgrip.store.db import open_db
from netgrip.store.pages import PageVersion
from netgrip.store.projections import append_and_project
from netgrip.store.rebuild import rebuild
from netgrip.store.settings import DEFAULT_SETTINGS, SettingsModel, resolve_investigation_settings

INV = "inv-1"


def src(credibility, origin, sid=None):
    return Source(
        id=sid or f"{credibility}-{origin}", url=f"https://{origin}/x", title=None,
        page_version_id="pv", credibility=credibility, published_at=None, origin_key=origin,
    )  # fmt: skip


P, R, W = "Primary", "Reputable", "Weak"


@pytest.mark.parametrize(
    "supporting, contradicting, threshold, expected",
    [
        ([], [], 2, "Unverified"),
        ([src(R, "a")], [], 1, "Confirmed"),  # Low effort: one credible source confirms
        ([src(P, "a")], [], 2, "Supported"),
        ([src(P, "a"), src(R, "b")], [], 2, "Confirmed"),
        ([src(R, "a"), src(R, "a", "other-article"), src(R, "a", "third")], [], 2, "Supported"),
        ([src(W, "a"), src(W, "b"), src(W, "c")], [], 2, "Unverified"),
        ([src(W, "a")], [], 1, "Unverified"),
        ([src(R, "a"), src(W, "b"), src(W, "c")], [], 2, "Supported"),
        ([], [src(R, "a"), src(P, "b")], 2, "Refuted"),
        ([], [src(R, "a")], 1, "Refuted"),
        ([], [src(R, "a")], 2, "Unverified"),
        ([], [src(R, "a"), src(R, "a", "second")], 2, "Unverified"),
        ([src(W, "w")], [src(R, "a"), src(R, "b")], 2, "Refuted"),
        ([src(R, "a")], [src(R, "b")], 2, "Contested"),
        ([src(R, "a"), src(P, "b")], [src(R, "c")], 2, "Contested"),
        ([src(R, "a")], [src(W, "b")], 2, "Supported"),
    ],
)
def test_claim_status(supporting, contradicting, threshold, expected):
    assert claim_status(supporting, contradicting, threshold) == expected


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    await append_and_project(
        d, INV,
        [EventDraft(type="investigation.created", actor="user",
                    data={"prompt": "p", "settings": {"spending_limit_usd": 5.0}})],
    )  # fmt: skip
    yield d
    await d.close()


def make_ctx(script, node_id="n1", effort="Medium"):
    g = SettingsModel.model_validate(DEFAULT_SETTINGS)
    return CallContext(
        client=FakeModelClient(script),
        investigation_id=INV,
        settings=resolve_investigation_settings(g, {"effort": effort}),
        prices=g.models,
        node_id=node_id,
    )


def pv(url="https://a.org/1"):
    return PageVersion("pv-" + url, url, datetime(2026, 1, 1, tzinfo=UTC), "r", "t", "T", None, 1)


@pytest.fixture
def svc(db):
    return EvidenceService(db)


async def source(svc, ctx, origin, cred="Reputable", n=1):
    return await svc.record_source(
        ctx, f"https://{origin}/{n}", pv(f"https://{origin}/{n}"), cred, None, origin
    )


async def test_claim_without_source_rejected(svc, db):
    ctx = make_ctx({})
    with pytest.raises(ValueError):
        await svc.add_claim(ctx, "n1", "The wall is long", [], [])
    assert await svc.known_claims(INV, "wall") == []


async def test_add_claim_sets_status_and_records_events(svc):
    ctx = make_ctx({}, effort="Low")
    s = await source(svc, ctx, "a.org")
    c = await svc.add_claim(ctx, "n1", "The wall is long", [s.id], [])
    assert c.status == "Confirmed"  # threshold 1
    [known] = await svc.known_claims(INV, "wall")
    assert known.id == c.id and known.supporting == [s.id]


async def test_weak_only_stays_unverified(svc):
    ctx = make_ctx({})
    ids = [(await source(svc, ctx, o, "Weak")).id for o in ("a.org", "b.org", "c.org")]
    c = await svc.add_claim(ctx, "n1", "Rumour", ids, [])
    assert c.status == "Unverified"


async def test_record_source_is_idempotent_per_page_version(svc, db):
    ctx = make_ctx({})
    a = await source(svc, ctx, "a.org")
    b = await source(svc, ctx, "a.org")
    assert a.id == b.id
    assert len(await db.read("SELECT 1 FROM sources")) == 1


async def test_same_claim_from_two_nodes_is_merged_not_duplicated(svc, db):
    ctx1 = make_ctx({}, node_id="n1")
    s1 = await source(svc, ctx1, "a.org")
    first = await svc.add_claim(ctx1, "n1", "The wall is 21,000 km long", [s1.id], [])
    await svc.reconcile(ctx1, first)  # nothing to compare with: no model call
    assert ctx1.client.calls == []

    script = {"evidence.match": [{"parsed": {"relation": "same", "claim_id": first.id}}]}
    ctx2 = make_ctx(script, node_id="n2")
    s2 = await source(svc, ctx2, "b.org")
    second = await svc.add_claim(ctx2, "n2", "The Great Wall measures 21,000 km", [s2.id], [])
    await svc.reconcile(ctx2, second)

    [call] = ctx2.client.calls
    assert (call.purpose, call.tier) == ("evidence.match", "fast")
    [only] = await svc.known_claims(INV, "wall")
    assert only.id == first.id
    assert set(only.supporting) == {s1.id, s2.id}
    assert only.status == "Confirmed"  # two credible origins, threshold 2
    # the spend of the call was committed with the merge
    assert len(await db.read("SELECT 1 FROM events WHERE type = 'spend.recorded'")) == 1
    assert ctx2.pending_events == []


async def test_contradiction_across_branches_recorded_and_both_contested(svc, db):
    ctx1 = make_ctx({}, node_id="n1")
    s1 = await source(svc, ctx1, "a.org")
    a = await svc.add_claim(ctx1, "n1", "The wall is visible from space", [s1.id], [])

    script = {
        "evidence.match": [{"parsed": {"relation": "contradicts", "claim_id": a.id}}],
        "evidence.contradiction": [{"parsed": {"contradicts": True}}],
    }
    ctx2 = make_ctx(script, node_id="n2")
    s2 = await source(svc, ctx2, "b.org")
    b = await svc.add_claim(ctx2, "n2", "The wall is not visible from space", [s2.id], [])
    await svc.reconcile(ctx2, b)

    assert [(c.purpose, c.tier) for c in ctx2.client.calls] == [
        ("evidence.match", "fast"),
        ("evidence.contradiction", "strong"),
    ]
    claims = {c.id: c for c in await svc.known_claims(INV, "wall")}
    assert claims[a.id].status == claims[b.id].status == "Contested"
    assert claims[a.id].contradicting == [s2.id]
    assert claims[b.id].contradicting == [s1.id]
    rows = await db.read("SELECT claim_a, claim_b FROM contradictions")
    assert [set(r) for r in rows] == [{a.id, b.id}]
    assert (
        len(await db.read("SELECT 1 FROM events WHERE type = 'claim.contradiction_recorded'")) == 1
    )


async def test_contradiction_judged_false_leaves_statuses(svc):
    ctx1 = make_ctx({})
    s1 = await source(svc, ctx1, "a.org")
    a = await svc.add_claim(ctx1, "n1", "A", [s1.id], [])
    script = {
        "evidence.match": [{"parsed": {"relation": "contradicts", "claim_id": a.id}}],
        "evidence.contradiction": [{"parsed": {"contradicts": False}}],
    }
    ctx2 = make_ctx(script, node_id="n2")
    s2 = await source(svc, ctx2, "b.org")
    b = await svc.add_claim(ctx2, "n2", "B", [s2.id], [])
    await svc.reconcile(ctx2, b)
    assert {c.status for c in await svc.known_claims(INV, "x")} == {"Supported"}


async def test_set_premise_outcome(svc, db):
    await append_and_project(
        db, INV,
        [EventDraft(type="premise.extracted", actor="orchestrator",
                    data={"premise_id": "p1", "text": "t", "node_id": None})],
    )  # fmt: skip
    await svc.set_premise_outcome(make_ctx({}), "p1", "refuted")
    rows = await db.read("SELECT outcome FROM premises WHERE id = 'p1'")
    assert rows[0]["outcome"] == "refuted"


async def test_evidence_state_is_rebuilt_from_the_log(svc, db):
    ctx1 = make_ctx({})
    s1 = await source(svc, ctx1, "a.org")
    a = await svc.add_claim(ctx1, "n1", "A", [s1.id], [])
    script = {
        "evidence.match": [{"parsed": {"relation": "contradicts", "claim_id": a.id}}],
        "evidence.contradiction": [{"parsed": {"contradicts": True}}],
    }
    ctx2 = make_ctx(script, node_id="n2")
    s2 = await source(svc, ctx2, "b.org")
    b = await svc.add_claim(ctx2, "n2", "B", [s2.id], [])
    await svc.reconcile(ctx2, b)

    async def dump():
        return [
            [tuple(r) for r in await db.read(f"SELECT * FROM {t} ORDER BY 1, 2")]
            for t in ("sources", "claims", "claim_sources", "contradictions")
        ]

    before = await dump()
    await rebuild(db)
    assert await dump() == before
