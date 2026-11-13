import type { ClaimStatus as Status, ReportClaim, ReportStatement as Data } from "../api/types";
import { ClaimStatus } from "./ClaimStatus";
import { cx } from "./cx";

const WEAKEST_FIRST: Status[] = ["Refuted", "Contested", "Unverified", "Supported", "Confirmed"];

/** The weakest status among the claims a statement cites: what its pill says. */
export function weakest(statement: Data, claims: Record<string, ReportClaim>): Status | null {
  const found = statement.claim_ids.flatMap((id) => (claims[id] ? [claims[id].status] : []));
  return found.length ? found.reduce((a, b) => (WEAKEST_FIRST.indexOf(b) < WEAKEST_FIRST.indexOf(a) ? b : a)) : null;
}

/** `ng-cite` chips: the claim's label, or the premise node's id (P1) for a premise. The open
 * one is filled. A chip toggles the evidence pane. */
export function Cites({ ids, claims, openId, onCite, premise }: {
  ids: string[]; claims: Record<string, ReportClaim>; openId: string | null;
  onCite: (claimId: string) => void;
  /** "P1": the premise this statement is about, cited first. */
  premise?: { label: string; claimId: string | null } | null;
}) {
  const chip = (key: string, label: string, claimId: string | null) => (
    <a
      key={key}
      href={`#${label}`}
      role="button"
      aria-pressed={claimId != null && claimId === openId}
      className={cx("ng-cite", claimId != null && claimId === openId && "is-open")}
      onClick={(e) => { e.preventDefault(); if (claimId) onCite(claimId); }}
    >
      {label}
    </a>
  );
  return (
    <>
      {premise && chip(`premise-${premise.label}`, premise.label, premise.claimId)}
      {ids.flatMap((id) => (claims[id] ? [chip(id, claims[id].label, id)] : []))}
    </>
  );
}

/** One statement of the report: its words (dashed `ng-hedge` underline when it rests on a claim
 * below Confirmed), then its citations. `display` is the answer's first sentence. Text is data:
 * shown as characters only. */
export function ReportStatement({ statement, claims, openId, onCite, form = "para", pill, premise }: {
  statement: Data; claims: Record<string, ReportClaim>; openId: string | null;
  onCite: (claimId: string) => void;
  form?: "display" | "para" | "inline";
  /** The status pill before the words (findings and what could not be verified). */
  pill?: boolean;
  premise?: { label: string; claimId: string | null } | null;
}) {
  const status = pill ? weakest(statement, claims) : null;
  const words = statement.hedged ? <span className="ng-hedge">{statement.text}</span> : statement.text;
  const body = (
    <>
      {status && <><ClaimStatus status={status} />{" "}</>}
      {words}
      <Cites ids={statement.claim_ids} claims={claims} openId={openId} onCite={onCite} premise={premise} />
    </>
  );
  if (form === "display") return <h2 className="ng-display">{body}</h2>;
  if (form === "inline") return <span>{body}</span>;
  return <p>{body}</p>;
}
