"""Every model-call response schema is valid for strict structured output: the OpenAI-compatible
adapter sends "strict": true, and a provider refuses (or ignores) a schema that is not."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from netgrip.adapters.schema import fill_nulls, nullable, obj, strict_problems, string_enum
from netgrip.engine import instructions, orchestrator, planner, steps, synthesis
from netgrip.evidence import service

SRC = Path(__file__).parent.parent / "src" / "netgrip"


def _decide(kind: str, allowed: list[str]) -> dict:
    return steps._schema(SimpleNamespace(node=SimpleNamespace(kind=kind)), allowed)


SCHEMAS = {
    "PLAN_DRAFT_SCHEMA": planner.PLAN_DRAFT_SCHEMA,
    "_EXTRACT_SCHEMA": steps._EXTRACT_SCHEMA,
    "_schema": _decide("Divergent", steps.ACTIONS),
    "_schema (premise check)": _decide(steps.PREMISE_CHECK, ["conclude"]),
    "REVIEW_SCHEMA": orchestrator.REVIEW_SCHEMA,
    "RELEVANCE_SCHEMA": orchestrator.RELEVANCE_SCHEMA,
    "NEXT_SCHEMA": orchestrator.NEXT_SCHEMA,
    "_MATCH_SCHEMA": service._MATCH_SCHEMA,
    "_JUDGE_SCHEMA": service._JUDGE_SCHEMA,
    "CHILDREN_SCHEMA": instructions.CHILDREN_SCHEMA,
    "_SCHEMA": synthesis._SCHEMA,
}


@pytest.mark.parametrize("name", list(SCHEMAS))
def test_schema_is_strict_valid(name):
    assert strict_problems(SCHEMAS[name]) == []


def test_every_model_call_schema_is_covered():
    """A new `response_schema=` in the code base must be added to SCHEMAS above."""
    used = set()
    for f in SRC.rglob("*.py"):
        if "adapters" in f.parts:
            continue
        used |= set(re.findall(r"response_schema=([A-Za-z_]+)", f.read_text(encoding="utf-8")))
    assert used and used <= {n.split(" ")[0] for n in SCHEMAS}


def test_strict_problems_finds_the_usual_mistakes():
    loose = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"enum": ["x"]}},
        "required": ["a"],
    }
    problems = strict_problems(loose)
    assert any("additionalProperties" in p for p in problems)
    assert any("required" in p for p in problems)
    assert any("$.b: no type" in p for p in problems)
    bad_enum = obj({"a": {"type": "string", "enum": ["x", None]}})
    assert strict_problems(bad_enum) == ["$.a: enum value None does not match type 'string'"]
    assert strict_problems(obj({"a": nullable(string_enum(["x"]))})) == []


def test_fill_nulls_sets_omitted_nullable_fields_only():
    schema = obj(
        {
            "need": {"type": "string"},
            "opt": nullable({"type": "string"}),
            "kids": nullable({"type": "array", "items": obj({"q": {"type": "string"},
                                                              "k": nullable({"type": "string"})})}),
        }
    )  # fmt: skip
    assert fill_nulls({"kids": [{"q": "a"}]}, schema) == {
        "kids": [{"q": "a", "k": None}],
        "opt": None,
    }  # "need" is not nullable: left missing, so validation still refuses the answer
