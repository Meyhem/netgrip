import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { DurableEvent, Snapshot } from "../api/types";

/** The golden plan review contract written by backend/tests/test_contract_golden.py.
 * Tests run from frontend/, so the repo-root contract/ is one level up. */
export function planReviewContract(): { events: DurableEvent[]; snapshot: Snapshot } {
  return JSON.parse(readFileSync(resolve(process.cwd(), "../contract/plan_review.json"), "utf-8"));
}
