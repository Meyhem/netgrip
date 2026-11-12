import type { ClaimStatus, InvestigationState, NodeState, PauseCause, Inclusion } from "../api/types";
import { cx } from "./cx";
import { CLAIM_STATUS, INCLUSION_PILL, INVESTIGATION_PILL, NODE_PILL, PAUSE_ORIGIN, PILL_TONE_CLASS, type PillSpec } from "./vocab";

type Props =
  | { kind: "investigation"; state: InvestigationState; origin?: PauseCause | null; reconnecting?: boolean }
  | { kind: "node"; state: NodeState }
  | { kind: "inclusion"; state: Exclude<Inclusion, "Included"> }
  | { kind: "claim"; state: ClaimStatus };

export function Pill({ spec, word, still }: { spec: PillSpec; word?: string; still?: boolean }) {
  return (
    <span className={cx("ng-pill", PILL_TONE_CLASS[spec.tone], spec.ghost && "ng-pill--ghost", spec.hollow && "ng-pill--hollow")}>
      <i>{spec.pulses && !still ? <span className="ng-pulse">{spec.glyph}</span> : spec.glyph}</i>
      {word ?? spec.word}
    </span>
  );
}

export function StatusPill(props: Props) {
  switch (props.kind) {
    case "investigation": {
      const spec = INVESTIGATION_PILL[props.state];
      const word = props.state === "Paused" && props.origin ? `${spec.word} · ${PAUSE_ORIGIN[props.origin]}` : spec.word;
      return <Pill spec={spec} word={word} />;
    }
    case "node":
      return <Pill spec={NODE_PILL[props.state]} />;
    case "inclusion":
      return <Pill spec={INCLUSION_PILL[props.state]} />;
    case "claim":
      return <Pill spec={CLAIM_STATUS[props.state]} />;
  }
}
