import type { ButtonHTMLAttributes } from "react";
import { cx } from "./cx";

const VARIANT = { default: "", steer: "ng-btn--steer", quiet: "ng-btn--quiet", danger: "ng-btn--danger" } as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof VARIANT;
  size?: "sm";
  sent?: boolean;
  sentLabel?: string;
  kbd?: string;
}

/** A command button. `sent` holds the present participle until the confirming event arrives. */
export function Button({ variant = "default", size, sent, sentLabel, kbd, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={cx("ng-btn", VARIANT[variant], size === "sm" && "ng-btn--sm", sent && "is-sent", className)}
      disabled={disabled || sent}
    >
      {sent && sentLabel ? sentLabel : children}
      {kbd && !sent && <span className="ng-kbd">{kbd}</span>}
    </button>
  );
}
