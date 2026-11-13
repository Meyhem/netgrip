import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getJSON } from "../api/client";
import type { DurableEvent, PauseCause, Settings, Snapshot } from "../api/types";
import { money } from "../lib/format";
import type { useCommand } from "../state/useCommand";
import { Button } from "./Button";

type Command = ReturnType<typeof useCommand>;

const movedTo = (state: string) => (ev: DurableEvent) => ev.type === "investigation.state_changed" && ev.data.to === state;

/** The cause in plain words, for the title ("Paused: …"). */
const TITLE: Record<Exclude<PauseCause, "user">, string> = {
  spending_limit: "the spending limit was reached",
  model_unavailable: "the model service stopped responding",
  search_unavailable: "the search service stopped responding",
  key_rejected: "a key was rejected",
  credit_exhausted: "the provider has no credit left",
};

function Shell({ tone, glyph, title, children, actions }: { tone: "warn" | "danger"; glyph: string; title: string; children: ReactNode; actions: ReactNode }) {
  return (
    <div className={tone === "warn" ? "ng-banner ng-banner--warn" : "ng-banner ng-banner--danger"} role="alert">
      <span className="ng-banner__g">{glyph}</span>
      <div className="ng-col ng-grow">
        <span className="ng-banner__t">{title}</span>
        <span className="ng-small">{children}</span>
        <div className="ng-row">{actions}</div>
      </div>
    </div>
  );
}

/** SystemPause: shown between the header and the panes while Netgrip itself paused the
 * investigation. Not dismissible: the choices are the way out. A user pause shows nothing. */
export function SystemPause({ s, command, onShowErrors }: { s: Snapshot; command: Command; onShowErrors: () => void }) {
  const inv = s.investigation;
  const cause = inv.pause_cause;
  const [settings, setSettings] = useState<Settings | null>(null);
  const [raised, setRaised] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const paused = inv.state === "Paused" && cause !== null && cause !== "user";
  const needsSettings = paused && (cause === "spending_limit" || cause === "key_rejected" || cause === "credit_exhausted");
  // Fetched when the banner shows, and again on a key cause until the key is replaced.
  useEffect(() => {
    if (!needsSettings) return;
    let live = true;
    const load = () => getJSON<Settings>("/api/settings").then((v) => live && setSettings(v)).catch(() => {});
    load();
    if (cause === "spending_limit") return () => { live = false; };
    const t = setInterval(load, 5000);
    return () => { live = false; clearInterval(t); };
  }, [needsSettings, cause]);
  if (!paused || cause === null) return null;

  const done = s.nodes.filter((n) => n.depth >= 1 && n.status === "Completed").length;
  const resume = (steer: boolean, disabled = false) => (
    <Button size="sm" variant={steer ? "steer" : "default"} disabled={disabled} sent={command.isSent("resume")} sentLabel="Resuming…"
      onClick={() => void command.send("resume", { settledBy: movedTo("Running") })}>Resume</Button>
  );
  const finish = (
    <Button size="sm" sent={command.isSent("finish_now")} sentLabel="Finishing…" onClick={() => void command.send("finish_now", { settledBy: movedTo("Synthesising") })}>Finish now</Button>
  );
  const stop = (
    <Button size="sm" variant="quiet" sent={command.isSent("stop")} sentLabel="Stopping…" onClick={() => void command.send("stop", { settledBy: movedTo("Stopped") })}>Stop</Button>
  );
  const title = `Paused: ${TITLE[cause as keyof typeof TITLE]}`;

  if (cause === "spending_limit") {
    const limit = inv.spending_limit_usd;
    const suggested = Math.round((limit + (settings?.spending_limit_usd ?? limit)) * 100) / 100;
    const value = raised ?? String(suggested);
    const amount = Number(value);
    const valid = Number.isFinite(amount) && amount > inv.spent_usd;
    const sent = busy || command.isSent("raise_limit") || command.isSent("resume");
    const raiseAndResume = async () => {
      setBusy(true);
      // Two commands, in this order: the limit first, so resume finds room to run.
      if (!(await command.send("raise_limit", { payload: { spending_limit_usd: amount } }))) return setBusy(false);
      if (!(await command.send("resume", { settledBy: movedTo("Running") }))) setBusy(false);
    };
    return (
      <Shell tone="warn" glyph="‖" title={`Paused: the spending limit of ${money(limit)} was reached`}
        actions={
          <>
            <label className="ng-row ng-row--tight">
              <span className="ng-label">New limit $</span>
              <input className="ng-input" style={{ width: 90 }} inputMode="decimal" aria-label="New spending limit" value={value}
                onChange={(e) => setRaised(e.target.value)} />
            </label>
            <Button size="sm" variant="steer" disabled={!valid} sent={sent} sentLabel="Resuming…" onClick={() => void raiseAndResume()}>Raise limit and resume</Button>
            {finish}
            {stop}
          </>
        }>
        {done} of {s.nodes.filter((n) => n.depth >= 1 && n.status !== "Rejected" && n.status !== "Proposed").length} nodes are complete. Nothing is lost. Choose how to continue.
      </Shell>
    );
  }

  if (cause === "model_unavailable" || cause === "search_unavailable") {
    return (
      <Shell tone="warn" glyph="‖" title={title}
        actions={
          <>
            {resume(true)}
            <Button size="sm" variant="quiet" onClick={onShowErrors}>Show the errors in the log</Button>
          </>
        }>
        {inv.pause_detail ? `${inv.pause_detail} ` : ""}Netgrip stopped retrying so it would not spend without progress. Nothing is lost.
      </Shell>
    );
  }

  const rejected = settings ? Object.values(settings.keys).some((k) => k.status === "rejected") : cause === "key_rejected";
  const blocked = cause === "key_rejected" && rejected;
  return (
    <Shell tone="danger" glyph="✕" title={title}
      actions={
        <>
          <Link className="ng-btn ng-btn--sm ng-btn--steer" to="/settings">Open Settings → Keys</Link>
          {resume(false, blocked)}
        </>
      }>
      {inv.pause_detail ?? "The provider refused the key."} {blocked ? "Replace the key, then resume." : "Resume when it is fixed."} Nothing is lost.
    </Shell>
  );
}

/** The newest `system.recovered` event this browser has not shown yet, once per recovery. */
export function useRecoveryNotice(investigationId: string, events: DurableEvent[]): { notice: DurableEvent | null; dismiss: () => void } {
  const key = `netgrip.recovered.${investigationId}`;
  const latest = [...events].reverse().find((e) => e.type === "system.recovered") ?? null;
  const [shown, setShown] = useState<number | null>(null);
  const seen = (() => {
    try { return Number(localStorage.getItem(key) ?? 0); } catch { return 0; }
  })();
  const notice = latest && (shown === latest.seq || latest.seq > seen) ? latest : null;
  useEffect(() => {
    if (!latest || latest.seq <= seen) return;
    // Seen from now on: a reload does not show it again.
    setShown(latest.seq);
    try { localStorage.setItem(key, String(latest.seq)); } catch { /* the notice may repeat */ }
  }, [latest?.seq]); // eslint-disable-line react-hooks/exhaustive-deps
  return { notice, dismiss: () => setShown(-1) };
}

export function RecoveryNotice({ event, onDismiss }: { event: DurableEvent; onDismiss: () => void }) {
  const n = (event.data.reset_node_ids as string[] | undefined)?.length ?? 0;
  return (
    <div className="ng-banner" role="status">
      <span className="ng-banner__g ng-live">↻</span>
      <div className="ng-col ng-grow">
        <span style={{ fontWeight: 600 }}>Picked up where it stopped.</span>
        <span className="ng-small ng-muted">
          {n > 0
            ? `Netgrip was shut down with ${n} ${n === 1 ? "node" : "nodes"} running. They are running again and reuse the pages already fetched.`
            : "Netgrip was shut down. The run continued by itself."}
        </span>
      </div>
      <Button size="sm" variant="quiet" onClick={onDismiss}>Dismiss</Button>
    </div>
  );
}
