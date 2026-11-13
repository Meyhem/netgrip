import type { NodeDetail } from "../api/types";

/** The Trail tab's content until Task 7 replaces it with the Trail component. */
export function TrailPlaceholder({ detail }: { detail: NodeDetail }) {
  return <p className="ng-small ng-muted">{detail.trail.length} steps recorded.</p>;
}
