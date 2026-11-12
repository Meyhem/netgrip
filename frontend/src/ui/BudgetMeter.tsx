import { money } from "../lib/format";
import { cx } from "./cx";

export function BudgetMeter({ label, value, max, format, approximate }: {
  label: string; value: number; max: number; format: "money" | "count"; approximate?: boolean;
}) {
  const ratio = max > 0 ? value / max : 0;
  const show = format === "money" ? money : (n: number) => String(n);
  return (
    <div className={cx("ng-meter", ratio >= 1 ? "ng-meter--danger" : ratio > 0.8 && "ng-meter--warn")}>
      <div className="ng-meter__top">
        <span className="ng-label">{label}</span>
        <span className="ng-meter__val">
          {approximate ? "≈ " : ""}{show(value)} <span>/ {show(max)}</span>
        </span>
      </div>
      <div className="ng-meter__track">
        <div className="ng-meter__fill" style={{ width: `${Math.min(100, Math.round(ratio * 100))}%` }} />
      </div>
    </div>
  );
}
