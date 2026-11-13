import type { NodeDetail, TrailStep } from "../api/types";
import { timeOfDaySeconds } from "../lib/format";
import type { ModelText } from "../state/investigationStore";
import { cx } from "./cx";

/** The fetch routes a read step can use, as the Trail names them (ScreenNodeDetail rules).
 * Only these name a route: other `route` values are decisions (search, read, …) or reuse. */
const FETCH_ROUTE: Record<string, string> = { simple: "simple fetch", browser: "full browser", hardened: "hardened browser" };

export const LIVE_NOT_STORED = "Live. This text is not stored.";

function verb(s: TrailStep): string {
  if (s.activity === "Retrying") return s.retry ? `Retrying ${s.retry.n} of ${s.retry.m}` : "Retrying";
  if (s.activity === "Waiting on children") return "Waiting";
  return s.activity ?? s.name;
}

/** Where an applied instruction was given: the node itself, or the ancestor it is inherited from. */
function instructionSource(detail: NodeDetail, id: string): string {
  const inherited = detail.instructions.inherited.find((i) => i.id === id);
  return inherited ? inherited.from_display_id : detail.node.display_id;
}

function ruleText(detail: NodeDetail, s: TrailStep, next: TrailStep | undefined): string {
  const ids = s.instruction_applied;
  const from = [...new Set(ids.map((id) => instructionSource(detail, id)))].join(", ");
  const what = ids.length === 1 ? "instruction" : `${ids.length} instructions`;
  const where = next ? `between step ${s.step} and step ${next.step}` : `after step ${s.step}`;
  return `— ${what} from ${from} applied here, ${where} —`;
}

/** ScreenNodeDetail, Trail tab: one well per step, oldest first. The open step streams the
 * model's text (never stored, D-11); closed steps show only what was persisted. */
export function Trail({ detail, modelText, onOpenPage, live, finished = false, halted = false }: {
  detail: NodeDetail;
  /** The node's streamed model text from the store, if any. Shown only on the matching open step. */
  modelText: ModelText | null;
  onOpenPage: (pageVersionId: string) => void;
  /** True only while the node runs (Running or Waiting on children), the investigation is not
   * paused and the stream is open. Otherwise the open step is a plain well: no live border, no text. */
  live: boolean;
  /** The node is Completed or Failed: a finished graph has no `live` in it, so verbs are muted. */
  finished?: boolean;
  /** The investigation is Paused or Stopped: nothing runs, so verbs are muted as well. */
  halted?: boolean;
}) {
  const steps = detail.trail;
  if (steps.length === 0) return <p className="ng-small ng-muted">No steps recorded yet.</p>;
  return (
    <div className="ng-col trail">
      {steps.map((s, i) => {
        const open = live && s.ended_at === null;
        const retry = s.activity === "Retrying";
        const text = open && modelText && modelText.node_id === detail.node.id && modelText.step === s.step ? modelText.text : null;
        const route = s.route && Object.hasOwn(FETCH_ROUTE, s.route) ? FETCH_ROUTE[s.route] : undefined;
        const what = [s.detail, route, s.summary].filter(Boolean).join(" · ");
        return [
          <div key={`s${s.step}`} data-step={s.step} className={cx("ng-well", "trail__step", open && "trail__step--open", retry && "trail__step--retry")}>
            <span className="ng-faint">step {s.step} · {timeOfDaySeconds(s.started_at)} · </span>
            <span className={cx("trail__verb", retry ? "ng-warn" : !finished && !halted && "ng-live")}>{verb(s).toUpperCase()}</span>
            {what && <> {what}</>}
            {s.page_version_id && <> <button type="button" className="trail__page" onClick={() => onOpenPage(s.page_version_id!)}>stored page</button></>}
            {text !== null && (
              <>
                <div className="ng-faint trail__live" key={`${detail.node.id}:${s.step}`}>{text}<span aria-hidden="true">▍</span></div>
                <div className="ng-faint trail__note">{LIVE_NOT_STORED}</div>
              </>
            )}
          </div>,
          s.instruction_applied.length > 0 && (
            <div key={`r${s.step}`} className="ng-well trail__rule">
              <span className="ng-steer">{ruleText(detail, s, steps[i + 1])}</span>
            </div>
          ),
        ];
      })}
    </div>
  );
}
