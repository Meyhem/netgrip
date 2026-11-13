"""The report query and its Markdown export (Phase 8, Task 3), on the fake Great Wall run."""

import asyncio
import re
import uuid

import pytest

from netgrip.config import Config
from netgrip.report.markdown import filename, to_markdown
from netgrip.report.model import Report
from netgrip.store.settings import set_key

PROMPT = "Is the Great Wall visible from space?"


@pytest.fixture
def config(tmp_path):
    return Config(data_dir=tmp_path / "data", fake=True)


async def post(client, inv, type, **payload):
    r = await client.post(
        f"/api/investigations/{inv}/commands",
        json={"id": str(uuid.uuid4()), "type": type, "node_id": None, "payload": payload},
    )
    assert r.status_code == 202, r.text


async def completed_run(client, prompt=PROMPT) -> str:
    inv = str(uuid.uuid4())
    r = await client.post("/api/investigations", json={"id": inv, "prompt": prompt})
    assert r.status_code == 202
    await post(client, inv, "draft_plan")
    for _ in range(100):  # the plan is drafted in the background
        if (await client.get(f"/api/investigations/{inv}")).json()["plan_version"]:
            break
        await asyncio.sleep(0.05)
    await post(client, inv, "approve_plan")
    for _ in range(400):
        state = (await client.get(f"/api/investigations/{inv}")).json()["investigation"]["state"]
        if state == "Completed":
            return inv
        await asyncio.sleep(0.05)
    raise AssertionError(f"not completed: {state}")


async def test_report_endpoint_includes_cited_claims_with_paths(app_client):
    inv = await completed_run(app_client)
    body = (await app_client.get(f"/api/investigations/{inv}/report")).json()
    assert [s["key"] for s in body["sections"]] == [
        "answer", "wrong", "findings", "unverified", "limits"]  # fmt: skip
    cited = {i for s in body["sections"] for st in s["statements"] for i in st["claim_ids"]}
    assert cited and cited <= set(body["claims"])
    claim = body["claims"][body["sections"][0]["statements"][0]["claim_ids"][0]]
    assert claim["supporting"][0]["url"].startswith("https://")
    assert [p["display_id"] for p in claim["path"]][0] == "R"
    assert claim["node_display_id"] == claim["path"][-1]["display_id"]
    assert re.fullmatch(r"C-\d{3}", claim["label"])
    [p1] = [p for p in body["premises"] if p["display_id"] == "P1"]
    assert (
        p1["outcome"] == "refuted"
        and p1["node_id"] == body["sections"][1]["statements"][0]["premise_node_id"]
    )
    assert body["totals"]["run_seconds"] >= 0
    row = (await app_client.get("/api/investigations")).json()[0]
    assert row["summary"].endswith("medium confidence")


async def test_markdown_has_sections_in_order_and_footnotes(app_client):
    inv = await completed_run(app_client)
    r = await app_client.get(f"/api/investigations/{inv}/report.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    text = r.text
    heads = re.findall(r"^## (.+)$", text, re.M)
    assert heads == ["The answer", "Where you were wrong", "Key findings",
                     "What could not be verified", "Limits of this investigation"]  # fmt: skip
    assert PROMPT in text.split("## ")[0]
    first = re.search(r"\[\^(c\d+)\]", text).group(1)
    assert re.search(rf"^\[\^{first}\]: .+\(Supported\)\. Sources: https://", text, re.M)
    assert "belief that it can is wrong. (Supported)[^c1]" in text  # hedged: status after wording


async def test_markdown_contains_no_settings_or_keys(app_client):
    engine = app_client.app.state.engine
    await set_key(engine.db, "model", "sk-very-secret-key")
    r = await app_client.patch("/api/settings", json={"excluded_domains": ["distinct-domain.test"]})
    assert r.status_code == 200, r.text
    inv = await completed_run(app_client)
    text = (await app_client.get(f"/api/investigations/{inv}/report.md")).text
    assert "sk-very-secret-key" not in text
    for name in ("effort_budget", "spending_limit", "sources_to_confirm", "tiers", "capacity",
                 "model_endpoint", "retry_before_pause"):  # fmt: skip
        assert name not in text
    assert text.count("distinct-domain.test") == 1
    assert text.index("distinct-domain.test") > text.index("## Limits of this investigation")


def test_markdown_filename_is_safe():
    name = filename('Is /etc/passwd "../../x"\nreal? ' + "long " * 30)
    assert re.fullmatch(r"[a-z0-9-]+\.md", name) and len(name) <= 64
    assert filename("???") == "report.md"


async def test_download_filename_comes_from_the_prompt(app_client):
    inv = await completed_run(app_client, "Wall/with\nnewline?")
    r = await app_client.get(f"/api/investigations/{inv}/report.md")
    assert 'filename="wall-with-newline.md"' in r.headers["content-disposition"]


async def test_no_report_is_404(app_client):
    inv = str(uuid.uuid4())
    await app_client.post("/api/investigations", json={"id": inv, "prompt": PROMPT})
    for path in ("report", "report.md"):
        r = await app_client.get(f"/api/investigations/{inv}/{path}")
        assert r.status_code == 404 and r.json()["code"] == "no_report"
    assert (await app_client.get("/api/investigations/nope/report")).status_code == 404


def test_hedged_status_and_unknown_claims_in_markdown():
    report = Report.model_validate({
        "id": "r", "investigation_id": "i", "created_at": "t", "answer_confidence": "low",
        "limits": {"effort": "Low", "confirm_threshold": 1},
        "sections": [
            {"key": "answer", "title": "The answer",
             "statements": [{"text": "Maybe.", "claim_ids": ["a"], "hedged": True}]},
            {"key": "findings", "title": "Key findings", "statements": []},
            {"key": "unverified", "title": "What could not be verified", "statements": []},
            {"key": "limits", "title": "Limits of this investigation", "statements": []},
        ],
    })  # fmt: skip
    claims = {"a": {"text": "A", "status": "Unverified", "supporting": [], "contradicting": []}}
    md = to_markdown(report, claims, "Q?")
    assert "Maybe. (Unverified)[^c1]" in md and "[^c1]: A (Unverified)" in md
