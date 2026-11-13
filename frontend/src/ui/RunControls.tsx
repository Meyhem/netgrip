import { Link } from "react-router-dom";
import type { DurableEvent, InvestigationState, Snapshot } from "../api/types";
import type { useCommand } from "../state/useCommand";
import { Button } from "./Button";

type Command = ReturnType<typeof useCommand>;

interface Control {
  label: string;
  type: string;
  sentLabel: string;
  steer?: boolean;
  /** The durable event that shows the command took effect. */
  settledBy: (ev: DurableEvent) => boolean;
}

const movedTo = (...states: InvestigationState[]) => (ev: DurableEvent) =>
  ev.type === "investigation.state_changed" && states.includes(ev.data.to as InvestigationState);

const PAUSE: Control = { label: "‖ Pause", type: "pause", sentLabel: "Pausing…", settledBy: movedTo("Paused", "Stopped", "Synthesising") };
const RESUME: Control = { label: "Resume", type: "resume", sentLabel: "Resuming…", steer: true, settledBy: movedTo("Running") };
const FINISH: Control = { label: "Finish now", type: "finish_now", sentLabel: "Finishing…", settledBy: movedTo("Synthesising", "Completed") };
const STOP: Control = { label: "Stop", type: "stop", sentLabel: "Stopping…", settledBy: movedTo("Stopped") };
const APPROVE: Control = { label: "Approve plan", type: "approve_plan", sentLabel: "Approving…", steer: true, settledBy: movedTo("Running") };

/** The commands each state offers (RunControls README). Synthesising and Completed have none
 * that send; Completed links to the report. */
export const CONTROLS: Record<InvestigationState, Control[]> = {
  Draft: [],
  Planning: [APPROVE],
  Running: [PAUSE, FINISH, STOP],
  Paused: [RESUME, FINISH, STOP],
  Synthesising: [],
  Stopped: [RESUME, { ...FINISH, label: "Finish into a report" }],
  Completed: [],
};

/** RunControls: the investigation-level commands at the right of the board header. Nothing
 * asks "are you sure"; a click holds the present participle (`is-sent`) until the event that
 * shows the effect arrives. While a system pause banner shows it owns the one steer button, so
 * Resume here is an ordinary button. */
export function RunControls({ s, command, bannerShown, onDiscard }: {
  s: Snapshot; command: Command; bannerShown?: boolean; onDiscard?: () => void;
}) {
  const inv = s.investigation;
  const state = inv.state;
  return (
    <>
      {CONTROLS[state].map((c) => (
        <Button
          key={c.type}
          size="sm"
          variant={c.steer && !(bannerShown && c.type === "resume") ? "steer" : "default"}
          sent={command.isSent(c.type)}
          sentLabel={c.sentLabel}
          onClick={() => void command.send(c.type, { settledBy: c.settledBy })}
        >
          {c.label}
        </Button>
      ))}
      {state === "Planning" && onDiscard && <Button size="sm" variant="quiet" onClick={onDiscard}>Discard draft</Button>}
      {state === "Completed" && (
        <>
          <Link className="ng-btn ng-btn--sm" to={`/investigations/${encodeURIComponent(inv.id)}`}>Open report</Link>
          <a className="ng-btn ng-btn--sm" href={`/api/investigations/${encodeURIComponent(inv.id)}/report.md`} download>Export Markdown</a>
        </>
      )}
    </>
  );
}
