import type { Activity } from "../api/types";
import { cx } from "./cx";

export function ActivityLine({ activity, detail, retry }: { activity: Activity; detail: string; retry?: { n: number; m: number } | null }) {
  const isRetry = activity === "Retrying";
  const verb = isRetry && retry ? `Retrying ${retry.n} of ${retry.m}` : activity === "Waiting on children" ? "Waiting" : activity;
  return (
    <div className="ng-activity">
      <span className={cx("ng-activity__verb", isRetry && "is-retry")}>{verb}</span>
      <span className="ng-activity__what">{detail}</span>
    </div>
  );
}
