"""The Markdown export (D-16): generated from the stored structure. It holds the prompt, the
sections and the limits; never settings and never keys."""

import re
from typing import Any

from netgrip.report.model import Report, Statement

STATUS_ORDER = ["Refuted", "Contested", "Unverified", "Supported", "Confirmed"]


def filename(prompt: str) -> str:
    """A safe download name from the first 60 characters of the prompt."""
    slug = re.sub(r"[^a-z0-9]+", "-", prompt[:60].lower()).strip("-")
    return f"{slug or 'report'}.md"


def _weakest(statement: Statement, claims: dict[str, dict[str, Any]]) -> str | None:
    statuses = [claims[i]["status"] for i in statement.claim_ids if i in claims]
    return min(statuses, key=STATUS_ORDER.index) if statuses else None


def to_markdown(report: Report, claims: dict[str, dict[str, Any]], prompt: str) -> str:
    """`claims`: the cited claims by id, as `GET .../report` returns them (text, status and
    supporting/contradicting sources with their URLs)."""
    labels: dict[str, str] = {}  # claim id -> footnote label, in order of first citation

    def cite(statement: Statement) -> str:
        marks = []
        for cid in statement.claim_ids:
            if cid in claims:
                marks.append(f"[^{labels.setdefault(cid, f'c{len(labels) + 1}')}]")
        return "".join(marks)

    def line(statement: Statement) -> str:
        text = statement.text.strip()
        if statement.hedged and (status := _weakest(statement, claims)):
            text += f" ({status})"
        return f"{text}{cite(statement)}"

    quoted = "\n".join(f"> {row}" if row else ">" for row in prompt.strip().splitlines())
    out = ["# Research report", "", quoted, ""]
    for section in report.sections:
        out += [f"## {section.title}", ""]
        if section.key == "limits":
            out += [f"- {s.text}" for s in section.statements]
            out += _limits(report)
        elif section.key == "answer" and section.statements:
            out.append(line(section.statements[0]))
            out += ["", *(line(s) for s in section.statements[1:])]
        else:
            out += [f"- {line(s)}" for s in section.statements] or ["Nothing to report."]
        out.append("")
    for cid, label in labels.items():
        c = claims[cid]
        urls = [s["url"] for s in c.get("supporting", [])]
        against = [s["url"] for s in c.get("contradicting", [])]
        note = f"[^{label}]: {c['text']} ({c['status']})"
        if urls:
            note += ". Sources: " + ", ".join(urls)
        if against:
            note += ". Against: " + ", ".join(against)
        out.append(note)
    return "\n".join(out).rstrip() + "\n"


def _limits(report: Report) -> list[str]:
    lim = report.limits
    rows: list[str] = []
    for b in lim.excluded_branches:
        who = "you" if b.by == "user" else "a change of plan"
        rows.append(f"- Branch {b.display_id} was left out by {who}: {b.question}")
    for i in lim.instructions:
        where = f" (to {i.node_display_id})" if i.node_display_id else ""
        rows.append(f"- Instruction{where}: {i.text}")
    if lim.unobtainable_pages:
        rows.append("- Pages that could not be obtained: " + ", ".join(lim.unobtainable_pages))
    if lim.excluded_domains:
        rows.append("- Domains excluded from search: " + ", ".join(lim.excluded_domains))
    return rows
