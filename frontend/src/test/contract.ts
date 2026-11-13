import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { DurableEvent, Snapshot } from "../api/types";

/** Tests run from frontend/, so the repo-root contract/ is one level up. */
const read = (name: string) => JSON.parse(readFileSync(resolve(process.cwd(), "../contract", name), "utf-8"));

/** The golden plan review contract written by backend/tests/test_contract_golden.py. */
export function planReviewContract(): { events: DurableEvent[]; snapshot: Snapshot } {
  return read("plan_review.json");
}

/** The golden full run (draft to Completed) written by backend/tests/test_contract_golden.py:
 * every durable event, then snapshots in seq order (one mid-run, the last one final). */
export function runContract(): { events: DurableEvent[]; snapshots: Snapshot[] } {
  return read("run.json");
}
