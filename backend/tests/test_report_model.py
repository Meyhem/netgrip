import pytest

from netgrip.evidence.service import Claim
from netgrip.report.model import TITLES, Limits, Report, Section, Statement, validate_report


def claim(id, status="Confirmed"):
    return Claim(id, "inv", "n1", f"text {id}", status)


CLAIMS = {"c1": claim("c1"), "c2": claim("c2", "Supported")}


def make(*, wrong=None, answer=None, findings=None, order=None, titles=None) -> Report:
    sections = {
        "answer": answer if answer is not None else [Statement(text="A", claim_ids=["c1"])],
        "wrong": wrong,
        "findings": findings if findings is not None else [Statement(text="F", claim_ids=["c1"])],
        "unverified": [],
        "limits": [],
    }
    keys = order or [k for k in TITLES if sections[k] is not None]
    secs = [
        Section(key=k, title=(titles or {}).get(k, TITLES[k]), statements=sections[k] or [])
        for k in keys
    ]
    return Report(
        id="r", investigation_id="inv", created_at="t", answer_confidence="high",
        sections=secs, limits=Limits(effort="Medium", confirm_threshold=2),
    )  # fmt: skip


def errors(report, **kw):
    return validate_report(report, CLAIMS, **kw)


def test_valid_report_passes():
    assert errors(make()) == []


def test_valid_report_with_refuted_premise_passes():
    wrong = [Statement(text="W", claim_ids=["c1"], premise_node_id="p1")]
    assert errors(make(wrong=wrong), refuted_premises=["p1"]) == []


def test_wrong_order_is_an_error():
    r = make(order=["findings", "answer", "unverified", "limits"])
    assert any("sections must be" in e for e in errors(r))


def test_wrong_title_is_an_error():
    assert any("titled" in e for e in errors(make(titles={"answer": "Result"})))


def test_missing_section_is_an_error():
    r = make(order=["answer", "findings", "limits"])
    assert any("sections must be" in e for e in errors(r))


def test_statement_without_claims_is_an_error():
    r = make(answer=[Statement(text="No cite")])
    assert any("cites no claim" in e for e in errors(r))


def test_limits_section_needs_no_claims():
    r = make()
    r.section("limits").statements.append(Statement(text="Ended early"))
    assert errors(r) == []


def test_unknown_claim_id_is_an_error():
    r = make(answer=[Statement(text="A", claim_ids=["nope"])])
    assert any("unknown claim nope" in e for e in errors(r))


def test_claim_of_excluded_node_is_an_error():
    r = make(answer=[Statement(text="A", claim_ids=["c1"])])
    assert any("excluded or off-topic" in e for e in errors(r, excluded_claim_ids=["c1"]))


def test_below_confirmed_must_be_hedged():
    r = make(answer=[Statement(text="A", claim_ids=["c2"], hedged=False)])
    assert any("not hedged" in e for e in errors(r))
    r = make(answer=[Statement(text="A", claim_ids=["c2"], hedged=True)])
    assert errors(r) == []


def test_mixed_confirmed_and_supported_need_no_hedge():
    r = make(answer=[Statement(text="A", claim_ids=["c1", "c2"])])
    assert errors(r) == []


def test_refuted_premise_without_wrong_statement_is_an_error():
    assert any("no statement in 'wrong'" in e for e in errors(make(), refuted_premises=["p1"]))


def test_wrong_without_refuted_premise_is_an_error():
    wrong = [Statement(text="W", claim_ids=["c1"], premise_node_id="p1")]
    assert any("no premise was refuted" in e for e in errors(make(wrong=wrong)))


@pytest.mark.parametrize("n", [0])
def test_empty_answer_is_valid_structurally(n):
    assert errors(make(answer=[])) == []
