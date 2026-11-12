import type { ReactNode } from "react";
import { useParams } from "react-router-dom";
import { ApiError, getJSON } from "../api/client";
import type { InvestigationState, Snapshot } from "../api/types";
import { usePoll } from "../lib/usePoll";
import { Banner } from "../ui/Banner";
import { INVESTIGATION_PILL } from "../ui/vocab";
import { NewInvestigation } from "./NewInvestigation";

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

export function NotBuilt({ state }: { state: InvestigationState }) {
  return (
    <Page>
      <Banner title={`This investigation is in ${INVESTIGATION_PILL[state].word}.`}>
        Its screen arrives in a later phase. Nothing is lost.
      </Banner>
    </Page>
  );
}

export function InvestigationRoute({ board = false }: { board?: boolean }) {
  const { id = "" } = useParams();
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
  if (name === "NewInvestigation") return <NewInvestigation draft={data.investigation} />;
  return <NotBuilt state={state} />;
}
