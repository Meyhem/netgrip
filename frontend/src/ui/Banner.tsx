import type { ReactNode } from "react";

const TONE = { info: "", warn: "ng-banner--warn", danger: "ng-banner--danger", steer: "ng-banner--steer" } as const;
const GLYPH = { info: "·", warn: "‖", danger: "✕", steer: "✎︎" } as const;

export function Banner({ tone = "info", title, children, glyph }: {
  tone?: keyof typeof TONE; title: ReactNode; children?: ReactNode; glyph?: string;
}) {
  return (
    <div className={`ng-banner ${TONE[tone]}`.trim()} role={tone === "warn" || tone === "danger" ? "alert" : "status"}>
      <span className="ng-banner__g">{glyph ?? GLYPH[tone]}</span>
      <div className="ng-col" style={{ gap: 2 }}>
        <span className="ng-banner__t">{title}</span>
        {children && <span className="ng-small">{children}</span>}
      </div>
    </div>
  );
}
