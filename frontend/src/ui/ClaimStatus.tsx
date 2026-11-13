import type { ClaimStatus as Status } from "../api/types";
import { StatusPill } from "./StatusPill";

/** A claim's status as the evidence service computed it; the UI never derives one. */
export function ClaimStatus({ status }: { status: Status }) {
  return <StatusPill kind="claim" state={status} />;
}
