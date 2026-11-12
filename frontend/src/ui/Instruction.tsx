import type { Instruction as InstructionData } from "../api/types";
import { cx } from "./cx";

export type InstructionVariant = "queued" | "applied" | "inherited";

/** "#" and four digits: every instruction links to its event in the log by sequence number. */
export const seqLabel = (seq: number) => `#${String(seq).padStart(4, "0")}`;

const VARIANT_CLASS: Record<InstructionVariant, string | null> = {
  applied: null,
  queued: "ng-instr--queued",
  inherited: "ng-instr--inherited",
};

/** A sent instruction, verbatim, with its `ng-diff` once applied. */
export function Instruction({ instruction, nodeDisplayIds, nodeQuestions = {}, variant, versionLabel, from, waitingFor }: {
  instruction: InstructionData;
  nodeDisplayIds: Record<string, string>;
  /** Questions for superseded and proposed nodes, shown after their ids. */
  nodeQuestions?: Record<string, string>;
  variant: InstructionVariant;
  /** "plan v1 → v2", when known. */
  versionLabel?: string;
  /** Inherited: the display id of the node it was given to. */
  from?: string;
  /** Queued: what it is waiting for. */
  waitingFor?: string;
}) {
  const i = instruction;
  const name = (id: string) => nodeDisplayIds[id] ?? "?";
  const named = (id: string) => [name(id), nodeQuestions[id]].filter(Boolean).join(" ");
  const sent = `You · ${seqLabel(i.queued_seq)}`;
  const status =
    variant === "queued"
      ? `queued · ${waitingFor ?? "applies when the re-plan is drawn"}`
      : i.state === "undone"
        ? "undone"
        : [versionLabel, i.applied_seq != null ? `applied ${seqLabel(i.applied_seq)}` : null].filter(Boolean).join(" · ");
  const d = variant === "queued" ? null : i.diff;
  const hasDiff = d && (d.kept.length || d.superseded.length || d.proposed.length || d.notes.length);

  return (
    <div className={cx("ng-instr", VARIANT_CLASS[variant])}>
      <div className="ng-instr__meta">
        {variant === "inherited" ? <><span>Inherited from {from}</span><span>{sent}</span></> : <><span>{sent}</span><span>{status}</span></>}
      </div>
      <div className="ng-instr__text">{i.text}</div>
      {d && hasDiff ? (
        <div className="ng-diff instr-diff">
          {d.kept.length > 0 && <span className="ng-diff__k">{"= kept".padEnd(14)}{d.kept.map(name).join(", ")}</span>}
          {d.superseded.map((id) => <span key={`s-${id}`} className="ng-diff__s">{"↺ superseded".padEnd(14)}{named(id)}</span>)}
          {d.proposed.map((id) => <span key={`p-${id}`} className="ng-diff__n">{"+ proposed".padEnd(14)}{named(id)}</span>)}
          {d.notes.map((n, k) => <span key={`n-${k}`}>{n}</span>)}
        </div>
      ) : null}
    </div>
  );
}
