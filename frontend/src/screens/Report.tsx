import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getJSON } from "../api/client";
import type { Report as ReportData, ReportSection, ReportSectionKey, Snapshot } from "../api/types";
import { clock, money } from "../lib/format";
import { useInvestigation } from "../state/investigationStore";
import { useSelection } from "../state/selection";
import { Banner } from "../ui/Banner";
import { Confidence } from "../ui/Confidence";
import { EvidencePane } from "../ui/EvidencePane";
import { ReportStatement } from "../ui/ReportStatement";
import { StatusPill } from "../ui/StatusPill";
import { PRESET_WORD } from "./NewInvestigation";

const TITLES: [ReportSectionKey, string][] = [
  ["answer", "The answer"],
  ["wrong", "Where you were wrong"],
  ["findings", "Key findings"],
  ["unverified", "What could not be verified"],
  ["limits", "Limits of this investigation"],
];
const ITEM_WORD: Record<ReportSectionKey, string> = { answer: "sentence", wrong: "item", findings: "item", unverified: "item", limits: "item" };
const CUT_SHORT = {
  budget: "The research was cut short: the node budget was spent.",
  spending_limit: "The research was ended early at the spending limit.",
  finish_now: "Ended early by you.",
} as const;

/** The report of a Completed investigation, or its headings while it is written (screens.md). */
export function Report({ id }: { id: string }) {
  const { snapshot, status } = useInvestigation(id);
  const state = snapshot?.investigation.state;
  const [report, setReport] = useState<ReportData | null>(null);
  const [missing, setMissing] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const { select } = useSelection(id);

  useEffect(() => {
    if (state !== "Completed") return;
    let live = true;
    getJSON<ReportData>(`/api/investigations/${encodeURIComponent(id)}/report`).then(
      (r) => { if (live) { setReport(r); setMissing(null); } },
      (e) => { if (live) setMissing(e instanceof ApiError && e.code === "no_report" ? "This investigation has no stored report." : "The report could not be loaded."); },
    );
    return () => { live = false; };
  }, [id, state]);

  if (!snapshot) return null;
  const board = `/investigations/${encodeURIComponent(id)}/board`;
  const nodeDisplayIds = Object.fromEntries(snapshot.nodes.map((n) => [n.id, n.display_id]));
  const cite = (claimId: string) => {
    const next = openId === claimId ? null : claimId;
    setOpenId(next);
    const node = next ? report?.claims[next]?.node_id : null;
    if (node) select(node);  // the board opens on the same node (ReportStatement README)
  };
  const claim = openId && report ? report.claims[openId] : undefined;

  return (
    <div className="ng-board report" style={{ gridTemplateRows: "auto 1fr" }}>
      <Header s={snapshot} report={report} board={board} status={status} />
      {state === "Synthesising" && <Writing claims={snapshot.synthesis_claims ?? null} />}
      {state === "Completed" && !report && (
        <main className="ng-pane__scroll report__main">
          {missing ? <Banner tone="warn" title={missing}>Nothing else is lost; the board still shows the research.</Banner> : <div className="ng-activity"><span className="ng-activity__verb">Loading</span>{" "}<span className="ng-activity__what">the report</span></div>}
        </main>
      )}
      {state === "Completed" && report && (
        <div className={`report-body${claim ? "" : " report-body--closed"}`}>
          <Contents report={report} />
          <main className="ng-pane__scroll report__main">
            <ReportText report={report} openId={openId} onCite={cite} />
          </main>
          {claim && (
            <EvidencePane
              claim={claim}
              usedIn={usedIn(report, claim.id)}
              nodeDisplayIds={nodeDisplayIds}
              onClose={() => setOpenId(null)}
              onBoard={claim.node_id ? <Link to={board} onClick={() => select(claim.node_id)}>show on the board</Link> : null}
            />
          )}
        </div>
      )}
    </div>
  );
}

function Header({ s, report, board, status }: { s: Snapshot; report: ReportData | null; board: string; status: ReturnType<typeof useInvestigation>["status"] }) {
  const inv = s.investigation;
  const preset = inv.settings?.preset;
  const ended = report?.limits.ended_early ?? inv.ended_early;
  const line = [
    inv.effort, preset ? PRESET_WORD[preset] : null,
    report ? clock(report.totals.run_seconds) : null, money(inv.spent_usd),
    ended ? "ended early by you" : null,
  ].filter(Boolean).join(" · ");
  return (
    <div className="ng-board__head">
      <Link to="/" className="ng-btn ng-btn--sm ng-btn--quiet" aria-label="Back to investigations">←</Link>
      <div className="ng-col ng-grow board-head__title">
        <div className="ng-row ng-row--nowrap">
          <StatusPill kind="investigation" state={inv.state} origin={inv.pause_cause} reconnecting={status === "reconnecting"} />
          <span className="ng-mono ng-muted">{line}</span>
        </div>
        <h1 className="ng-title ng-clip" title={inv.prompt}>{inv.prompt}</h1>
      </div>
      <div className="ng-row ng-row--nowrap">
        <Link className="ng-btn" to={board}>Open the board</Link>
        {inv.state === "Completed" && (
          <a className="ng-btn" href={`/api/investigations/${encodeURIComponent(inv.id)}/report.md`} download>Export Markdown</a>
        )}
      </div>
    </div>
  );
}

/** Synthesising: the five headings, the count of claims, no prose. */
function Writing({ claims }: { claims: number | null }) {
  return (
    <div className="report-body report-body--closed">
      <nav className="ng-pane ng-pane--left ng-col report-nav" aria-label="Report">
        <span className="ng-label">Report</span>
        {TITLES.map(([k, t]) => <span key={k} className="ng-small ng-muted">{t}</span>)}
      </nav>
      <main className="ng-pane__scroll report__main">
        <div className="ng-report">
          {TITLES.map(([k, t], i) => (
            <section key={k}>
              <h3 className="ng-title">{t}</h3>
              {i === 0 && (
                <div className="ng-activity">
                  <span className="ng-activity__verb">Writing</span>{" "}
                  <span className="ng-activity__what">{claims == null ? "the report…" : `from ${claims} ${claims === 1 ? "claim" : "claims"}…`}</span>
                </div>
              )}
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}

function section(r: ReportData, key: ReportSectionKey): ReportSection | undefined {
  return r.sections.find((s) => s.key === key);
}

/** Region 2: section links with counts, the evidence bar in words, the totals. */
function Contents({ report }: { report: ReportData }) {
  const n = report.limits.confirm_threshold;
  const confirmed = Object.values(report.claims).filter((c) => c.status === "Confirmed").length;
  return (
    <nav className="ng-pane ng-pane--left ng-col report-nav" aria-label="Report">
      <span className="ng-label">Report</span>
      {TITLES.flatMap(([k, t]) => {
        const sec = section(report, k);
        if (!sec) return [];
        const count = k === "answer" || k === "limits" ? null : sec.statements.length;
        return [
          <a key={k} className={k === "wrong" ? "ng-small ng-danger" : k === "answer" ? "ng-small report-nav__first" : "ng-small ng-muted"} href={`#report-${k}`}>
            {t}{count != null ? ` · ${count}` : ""}
          </a>,
        ];
      })}
      <hr className="ng-hr" />
      <span className="ng-label">Evidence bar</span>
      <span className="ng-small ng-muted">{report.limits.effort} effort: a claim is Confirmed with {n} independent {n === 1 ? "source" : "sources"}.</span>
      <span className="ng-mono ng-muted report-nav__totals">
        {report.totals.claims} claims · {confirmed} cited confirmed<br />
        {report.totals.sources} sources · {report.limits.unobtainable_pages.length} unobtainable
      </span>
    </nav>
  );
}

function usedIn(report: ReportData, claimId: string): string[] {
  return report.sections.flatMap((sec) =>
    sec.key === "limits" ? [] : sec.statements.flatMap((st, i) => (st.claim_ids.includes(claimId) ? [`${sec.title}, ${ITEM_WORD[sec.key]} ${i + 1}`] : [])),
  );
}

/** Region 3: the report in a 680px column. */
function ReportText({ report, openId, onCite }: { report: ReportData; openId: string | null; onCite: (id: string) => void }) {
  const props = { claims: report.claims, openId, onCite };
  const answer = section(report, "answer");
  const wrong = section(report, "wrong");
  const premiseByNode = useMemo(() => Object.fromEntries(report.premises.map((p) => [p.node_id ?? "", p])), [report.premises]);
  const [first, ...rest] = answer?.statements ?? [];
  return (
    <div className="ng-report">
      {answer && (
        <section id="report-answer">
          <div className="ng-row"><span className="ng-label">{answer.title}</span><Confidence level={report.answer_confidence} /></div>
          {first && <ReportStatement statement={first} form="display" {...props} />}
          {rest.map((st, i) => <ReportStatement key={i} statement={st} {...props} />)}
        </section>
      )}
      {wrong && wrong.statements.length > 0 && (
        <section id="report-wrong">
          <div className="ng-banner ng-banner--danger" role="alert">
            <span className="ng-banner__g">✕</span>
            <div className="ng-col ng-grow">
              <span className="ng-banner__t">{wrong.title}</span>
              {wrong.statements.map((st, i) => {
                const p = st.premise_node_id ? premiseByNode[st.premise_node_id] : undefined;
                return (
                  <span key={i}>
                    {p && <>Your question assumed <b>{p.text}</b>. </>}
                    <ReportStatement
                      statement={st} form="inline" {...props}
                      premise={p?.display_id ? { label: p.display_id, claimId: st.claim_ids[0] ?? null } : null}
                    />
                  </span>
                );
              })}
            </div>
          </div>
        </section>
      )}
      {(["findings", "unverified"] as const).map((k) => {
        const sec = section(report, k);
        if (!sec) return null;
        return (
          <section key={k} id={`report-${k}`}>
            <h3 className="ng-title">{sec.title}</h3>
            {sec.statements.length === 0 && <p className="ng-muted">Nothing to report.</p>}
            {sec.statements.map((st, i) => <ReportStatement key={i} statement={st} pill {...props} />)}
          </section>
        );
      })}
      <Limits report={report} />
    </div>
  );
}

function Limits({ report }: { report: ReportData }) {
  const lim = report.limits;
  const sec = section(report, "limits");
  return (
    <section id="report-limits">
      <h3 className="ng-title">{sec?.title ?? "Limits of this investigation"}</h3>
      {sec?.statements.map((st, i) => <p key={i} className="ng-muted">{st.text}</p>)}
      {lim.cut_short_by && <p className="ng-muted">{CUT_SHORT[lim.cut_short_by]}</p>}
      {lim.unobtainable_pages.length > 0 && (
        <p className="ng-muted">
          {lim.unobtainable_pages.length} {lim.unobtainable_pages.length === 1 ? "page" : "pages"} could not be obtained: {lim.unobtainable_pages.join(", ")}.
        </p>
      )}
      {lim.excluded_branches.map((b) => (
        <div key={b.display_id} className="ng-instr">
          <div className="ng-instr__meta"><span>{b.by === "user" ? "You excluded" : "Left out by a change of plan"} · {b.display_id}</span><span>Ignored branch</span></div>
          <div className="ng-instr__text">{b.question}</div>
        </div>
      ))}
      {lim.instructions.map((i) => (
        <div key={i.seq} className="ng-instr">
          <div className="ng-instr__meta"><span>You narrowed{i.node_display_id ? ` · ${i.node_display_id}` : ""}</span><span>Instruction</span></div>
          <div className="ng-instr__text">{i.text}</div>
        </div>
      ))}
      {lim.excluded_domains.length > 0 && <p className="ng-muted">Domains excluded from search: {lim.excluded_domains.join(", ")}.</p>}
    </section>
  );
}
