import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { createInvestigation, deleteInvestigation, getJSON } from "../api/client";
import type { InvestigationRow, InvestigationState, PauseCause, Settings, Storage } from "../api/types";
import { bytes, money, moneyOf } from "../lib/format";
import { usePoll } from "../lib/usePoll";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { DeleteDialog } from "../ui/DeleteDialog";
import { Input, Seg } from "../ui/Field";
import { StatusPill } from "../ui/StatusPill";
import { Page } from "./InvestigationRoute";
import { PromptBox } from "./PromptBox";

const ACTIVE: InvestigationState[] = ["Running", "Planning", "Synthesising", "Paused"];
const needsYou = (r: InvestigationRow) => r.state === "Planning" || r.state === "Paused";

type Filter = "all" | "needs" | "running" | "finished";
const FILTERS: Record<Filter, (r: InvestigationRow) => boolean> = {
  all: () => true,
  needs: needsYou,
  running: (r) => r.state === "Running" || r.state === "Synthesising",
  finished: (r) => r.state === "Completed" || r.state === "Stopped",
};
const FILTER_WORD: Record<Filter, string> = { all: "All", needs: "Needs you", running: "Running", finished: "Finished" };

const rank = (r: InvestigationRow) => (needsYou(r) ? 0 : r.state === "Running" ? 1 : 2);
export function sortRows(rows: InvestigationRow[]): InvestigationRow[] {
  return [...rows].sort((a, b) => rank(a) - rank(b) || b.last_activity_at.localeCompare(a.last_activity_at));
}

/** One action per state; Synthesising has nothing to do but watch. */
const ACTION: Record<InvestigationState, { label: string; steer?: boolean }> = {
  Draft: { label: "Continue" },
  Planning: { label: "Review plan", steer: true },
  Running: { label: "‖ Pause" },
  Paused: { label: "Resume", steer: true },
  Stopped: { label: "Finish into a report" },
  Completed: { label: "Open report" },
  Synthesising: { label: "Open" },
};

const PAUSE_REASON: Record<PauseCause, string> = {
  user: "Paused by you.",
  spending_limit: "Reached the spending limit.",
  model_unavailable: "The model service stopped responding.",
  search_unavailable: "Web search stopped responding.",
  key_rejected: "A key was rejected.",
  credit_exhausted: "The model account ran out of credit.",
};

function line2(r: InvestigationRow): ReactNode {
  switch (r.state) {
    case "Running":
      return <><span className="ng-live">{r.running_count} running</span>{r.summary ? ` · ${r.summary}` : ""}</>;
    case "Paused":
      return <><span className="ng-warn">{r.pause_detail ?? (r.pause_cause ? PAUSE_REASON[r.pause_cause] : "Paused.")}</span> Nothing is lost.</>;
    case "Draft":
      return r.summary ?? "Not started. Prompt and settings saved.";
    case "Planning":
      return r.summary ?? "Plan ready. Research has not started.";
    case "Stopped":
      return r.summary ?? `Stopped at ${r.nodes_total} of ${r.nodes_max} nodes. Resume or finish into a report.`;
    case "Synthesising":
      return r.summary ?? "Writing the report.";
    case "Completed":
      return r.summary ?? "Report ready.";
  }
}

const clock = (s: number) => {
  const t = Math.max(0, Math.floor(s));
  return `${Math.floor(t / 3600)}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
};
const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });

function runTime(r: InvestigationRow): string {
  if (r.state === "Running" || r.state === "Paused" || r.state === "Synthesising") return clock(r.run_seconds);
  if (r.state === "Planning") return "waiting";
  return day(r.last_activity_at);
}

const finished = (r: InvestigationRow) => r.state === "Completed" || r.state === "Stopped";

function Row({ r, onOpen, onDelete }: { r: InvestigationRow; onOpen: () => void; onDelete: () => void }) {
  const [menu, setMenu] = useState(false);
  const action = ACTION[r.state];
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);
  const draft = r.state === "Draft";
  return (
    <tr className="clickable" onClick={onOpen}>
      <td>
        <div className="ng-col" style={{ gap: 2 }}>
          <span className="ng-heading ng-clip" title={r.prompt}>{r.prompt}</span>
          <span className="ng-mono ng-muted ng-clip">{line2(r)}</span>
        </div>
      </td>
      <td><StatusPill kind="investigation" state={r.state} origin={r.pause_cause} /></td>
      <td>{r.effort ?? "–"}</td>
      <td className="is-num">{draft ? "–" : `${r.nodes_total} / ${r.nodes_max}`}</td>
      <td className="is-num">
        {draft ? "–" : `${r.spend_approximate ? "≈ " : ""}${finished(r) ? money(r.spent_usd) : moneyOf(r.spent_usd, r.spending_limit_usd)}`}
      </td>
      <td className="is-num">{bytes(r.disk_bytes)}</td>
      <td className="is-num">{runTime(r)}</td>
      <td onClick={(e) => e.stopPropagation()}>
        <div className="ng-row ng-row--nowrap row-actions" ref={menuRef}>
          <Button size="sm" variant={action.steer ? "steer" : "default"} onClick={onOpen}>{action.label}</Button>
          <Button size="sm" variant="quiet" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>More</Button>
          {menu && (
            <div className="ng-menu row-menu" role="menu">
              <div className="ng-menu__item" role="menuitem" tabIndex={0}
                onClick={() => { setMenu(false); onDelete(); }}
                onKeyDown={(e) => { if (e.key === "Enter") { setMenu(false); onDelete(); } }}>
                <b>Delete investigation</b>
                <small>Removes it and frees its disk space. Asks first.</small>
              </div>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

function EmptyState({ onSaved }: { onSaved: () => void }) {
  const [prompt, setPrompt] = useState("");
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const idRef = useRef(crypto.randomUUID()); // one id per prompt: a double click creates one
  const navigate = useNavigate();
  const save = async () => {
    if (sent || !prompt.trim()) return;
    setSent(true);
    setFailed(null);
    try {
      await createInvestigation(idRef.current, prompt, {});
      onSaved();
    } catch (e) {
      setFailed(e instanceof Error ? e.message : "Not saved.");
      setSent(false);
    }
  };
  return (
    <div className="ng-col ng-col--loose">
      <p className="ng-muted">Ask a question or state a claim. Netgrip will check it, including the parts you take for granted.</p>
      <PromptBox value={prompt} onChange={setPrompt} autoFocus />
      {failed && <p className="ng-small ng-danger">{failed}</p>}
      <div className="ng-row">
        <Button onClick={() => navigate("/new", { state: { prompt } })} disabled={!prompt.trim()}>Choose settings</Button>
        <Button variant="quiet" onClick={save} sent={sent} sentLabel="Saving…" disabled={!prompt.trim()}>Save as draft</Button>
      </div>
    </div>
  );
}

export function Investigations() {
  const navigate = useNavigate();
  const list = usePoll(() => getJSON<InvestigationRow[]>("/api/investigations"), 3000);
  const { data: settings } = usePoll(() => getJSON<Settings>("/api/settings"), 0);
  const { data: storage } = usePoll(() => getJSON<Storage>("/api/system/storage"), 10000);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [deleting, setDeleting] = useState<InvestigationRow | null>(null);
  const rows = list.data;

  const waiting = rows?.filter(needsYou).length ?? 0;
  useEffect(() => {
    document.title = waiting > 0 ? `(${waiting}) Netgrip` : "Netgrip";
  }, [waiting]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (e.key.toLowerCase() !== "n" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (t.closest("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      navigate("/new");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  const shown = useMemo(() => {
    if (!rows) return [];
    const q = query.trim().toLowerCase();
    return sortRows(rows.filter(FILTERS[filter]).filter((r) => !q || r.prompt.toLowerCase().includes(q)));
  }, [rows, filter, query]);

  const active = rows?.filter((r) => ACTIVE.includes(r.state)).length ?? 0;
  const limit = settings?.capacity.investigations;
  const counts = Object.fromEntries((Object.keys(FILTERS) as Filter[]).map((f) => [f, rows?.filter(FILTERS[f]).length ?? 0]));

  return (
    <Page width={1280}>
      <div className="ng-row">
        <h1 className="ng-display">Investigations</h1>
        {rows && (
          <span className="ng-mono ng-muted">
            {limit != null ? `${active} active of ${limit} allowed` : `${active} active`}
            {storage ? ` · ${bytes(storage.total_bytes)} on disk` : ""}
          </span>
        )}
        <Button variant="steer" className="ng-right" kbd="N" onClick={() => navigate("/new")}>New investigation</Button>
      </div>
      {list.error != null && (
        <Banner tone="warn" title="Netgrip cannot reach its service.">
          {rows ? "Showing the last list it sent. " : ""}Retrying every 3 seconds. Nothing is lost.
        </Banner>
      )}
      {rows && rows.length === 0 && <EmptyState onSaved={() => void list.reload()} />}
      {rows && rows.length > 0 && (
        <>
          <div className="ng-row">
            <Seg
              aria-label="Filter"
              options={Object.keys(FILTERS) as Filter[]}
              value={filter}
              onChange={setFilter}
              labels={Object.fromEntries((Object.keys(FILTERS) as Filter[]).map((f) => [f, `${FILTER_WORD[f]} ${counts[f]}`]))}
            />
            <Input className="search" aria-label="Search" placeholder="Search prompts" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <div className="ng-panel">
            <table className="ng-table investigations-table">
              <colgroup>
                <col /><col className="w-state" /><col className="w-effort" /><col className="w-num" />
                <col className="w-spend" /><col className="w-num" /><col className="w-num" /><col className="w-action" />
              </colgroup>
              <thead>
                <tr>
                  <th>Prompt</th><th>State</th><th>Effort</th><th className="num">Nodes</th><th className="num">Spend</th>
                  <th className="num">Disk</th><th className="num">Run time</th><th></th>
                </tr>
              </thead>
              <tbody>
                {shown.map((r) => (
                  <Row key={r.id} r={r} onOpen={() => navigate(`/investigations/${r.id}`)} onDelete={() => setDeleting(r)} />
                ))}
              </tbody>
            </table>
            {shown.length === 0 && <p className="ng-small ng-muted ng-pad">No investigation matches.</p>}
          </div>
          <p className="ng-small ng-muted">Disk counts shared pages for every investigation that uses them, so the column can add up to more than the total.</p>
        </>
      )}
      {deleting && (
        <DeleteDialog
          prompt={deleting.prompt}
          diskBytes={deleting.disk_bytes}
          onCancel={() => setDeleting(null)}
          onDelete={async () => {
            await deleteInvestigation(deleting.id);
            setDeleting(null);
            await list.reload();
          }}
        />
      )}
    </Page>
  );
}
