import type { Confidence as Level } from "../api/types";

const WORD: Record<Level, string> = { low: "Low", medium: "Medium", high: "High" };
const BARS: Record<Level, number> = { low: 1, medium: 2, high: 3 };

/** A verdict's confidence: three bars and a word, never a percentage (Verdict README). */
export function Confidence({ level, className }: { level: Level; className?: string }) {
  return (
    <span className={className ? `ng-conf ${className}` : "ng-conf"}>
      <span className="ng-conf__bars">
        {[1, 2, 3].map((b) => <b key={b} className={b <= BARS[level] ? "is-on" : undefined} />)}
      </span>
      {WORD[level]} confidence
    </span>
  );
}
