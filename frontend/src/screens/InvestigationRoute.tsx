import type { ReactNode } from "react";
import { useLocation, useParams } from "react-router-dom";
import { ApiError, getJSON } from "../api/client";
import type { InvestigationState, PauseCause, Snapshot } from "../api/types";
import { usePoll } from "../lib/usePoll";
import { Banner } from "../ui/Banner";
import { StatusPill } from "../ui/StatusPill";
import { INVESTIGATION_PILL } from "../ui/vocab";
import { ControlBoard } from "./ControlBoard";
import { NewInvestigation } from "./NewInvestigation";
import { PlanReview } from "./PlanReview";

export type ScreenName = "NewInvestigation" | "PlanReview" | "ControlBoard" | "Report";

/** screens.md: the investigation's state chooses its screen. */
export function screenFor(state: InvestigationState): ScreenName {
  switch (state) {
    case "Draft": return "NewInvestigation";
    case "Planning": return "PlanReview";
    case "Completed": return "Report";
    default: return "ControlBoard";
  }
}

export function Page({ children, width }: { children: ReactNode; width?: number }) {
  return (
    <main className="ng-page">
      <div className="ng-page__in" style={width ? { maxWidth: width } : undefined}>{children}</div>
    </main>
  );
}

export function NotBuilt({ state, origin }: { state: InvestigationState; origin?: PauseCause | null }) {
  return (
    <Page>
      <div className="ng-row"><StatusPill kind="investigation" state={state} origin={origin} /></div>
      <Banner title={`This investigation is in ${INVESTIGATION_PILL[state].word}.`}>
        Its screen arrives in a later phase. Nothing is lost.
      </Banner>
    </Page>
  );
}

export function InvestigationRoute({ board = false }: { board?: boolean }) {
  const { id = "" } = useParams();
  const location = useLocation();
  // NewInvestigation opens the investigation as soon as draft_plan is recorded.
  const drafting = (location.state as { drafting?: boolean } | null)?.drafting === true;
  const { data, error } = usePoll(() => getJSON<Snapshot>(`/api/investigations/${encodeURIComponent(id)}`), 3000);
  if (!data) {
    if (error instanceof ApiError && error.status === 404) {
      return <Page><Banner tone="warn" title="No such investigation.">It may have been deleted.</Banner></Page>;
    }
    if (error) return <Page><Banner tone="warn" title="Netgrip cannot reach its service.">Retrying every 3 seconds. Nothing is lost.</Banner></Page>;
    return null;
  }
  const state = data.investigation.state;
  const name = board ? "ControlBoard" : screenFor(state);
  if (name === "PlanReview" || (name === "NewInvestigation" && drafting)) return <PlanReview id={id} />;
  if (name === "NewInvestigation") return <NewInvestigation draft={data.investigation} />;
  if (name === "ControlBoard") return <ControlBoard id={id} />;
  return <NotBuilt state={state} origin={data.investigation.pause_cause} />;
}
