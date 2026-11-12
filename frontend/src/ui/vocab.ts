// The fixed state → glyph, word, tone tables from the StatusPill and ClaimStatus READMEs.
import type { ClaimStatus, InvestigationState, Kind, NodeState, PauseCause, Inclusion } from "../api/types";

export type Tone = "idle" | "live" | "ok" | "warn" | "danger" | "steer";

export interface PillSpec {
  glyph: string;
  word: string;
  tone: Tone;
  ghost?: boolean;
  hollow?: boolean;
  pulses?: boolean;
}

export const INVESTIGATION_PILL: Record<InvestigationState, PillSpec> = {
  Draft: { glyph: "○", word: "Draft", tone: "idle" },
  Planning: { glyph: "✎︎", word: "Plan review", tone: "steer" },
  Running: { glyph: "●", word: "Running", tone: "live", pulses: true },
  Paused: { glyph: "‖", word: "Paused", tone: "warn" },
  Synthesising: { glyph: "◐", word: "Synthesising", tone: "live" },
  Completed: { glyph: "✓", word: "Completed", tone: "ok" },
  Stopped: { glyph: "■", word: "Stopped", tone: "idle" },
};

export const NODE_PILL: Record<NodeState, PillSpec> = {
  Proposed: { glyph: "◌", word: "Proposed", tone: "idle", ghost: true },
  Rejected: { glyph: "⊘", word: "Rejected", tone: "danger", hollow: true },
  Pending: { glyph: "○", word: "Pending", tone: "idle" },
  Running: { glyph: "●", word: "Running", tone: "live", pulses: true },
  "Waiting on children": { glyph: "◔", word: "Waiting on children", tone: "live", hollow: true },
  Paused: { glyph: "‖", word: "Paused", tone: "warn" },
  Completed: { glyph: "✓", word: "Completed", tone: "ok" },
  Failed: { glyph: "✕", word: "Failed", tone: "danger" },
};

/** Shown only when a node is not Included. */
export const INCLUSION_PILL: Record<Exclude<Inclusion, "Included">, PillSpec> = {
  Ignored: { glyph: "⦸", word: "Ignored by you", tone: "steer", hollow: true },
  Superseded: { glyph: "↺", word: "Superseded by re-plan", tone: "idle", ghost: true },
};

export const CLAIM_STATUS: Record<ClaimStatus, PillSpec> = {
  Confirmed: { glyph: "✓✓", word: "Confirmed", tone: "ok" },
  Supported: { glyph: "✓", word: "Supported", tone: "ok", hollow: true },
  Unverified: { glyph: "?", word: "Unverified", tone: "idle" },
  Contested: { glyph: "⇄", word: "Contested", tone: "warn" },
  Refuted: { glyph: "✕", word: "Refuted", tone: "danger" },
};

export const KIND_CODE: Record<Kind, string> = {
  "Premise check": "PRM",
  Divergent: "DIV",
  "Deep-dive": "DEEP",
  Verification: "VER",
  Synthesis: "SYN",
};

export const PAUSE_ORIGIN: Record<PauseCause, string> = {
  user: "by you",
  spending_limit: "spending limit",
  model_unavailable: "model service unavailable",
  search_unavailable: "search unavailable",
  key_rejected: "key rejected",
  credit_exhausted: "credit exhausted",
};

/** Class strings spelled out so the design contract test can see each one. */
export const PILL_TONE_CLASS: Record<Tone, string> = {
  idle: "",
  live: "ng-pill--live",
  ok: "ng-pill--ok",
  warn: "ng-pill--warn",
  danger: "ng-pill--danger",
  steer: "ng-pill--steer",
};
