import { useEffect, useId, useState, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import type { KeyStatus } from "../api/types";
import { Button } from "./Button";
import { cx } from "./cx";

export function Field({ label, hint, error, htmlFor, children }: {
  label: ReactNode; hint?: ReactNode; error?: ReactNode; htmlFor?: string; children: ReactNode;
}) {
  return (
    <div className="ng-field">
      {htmlFor ? <label className="ng-field__label" htmlFor={htmlFor}>{label}</label> : <span className="ng-field__label">{label}</span>}
      {children}
      {error ? <span className="ng-field__hint is-error">{error}</span> : hint ? <span className="ng-field__hint">{hint}</span> : null}
    </div>
  );
}

export function Input({ mono, error, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { mono?: boolean; error?: boolean }) {
  return <input {...rest} className={cx("ng-input", mono && "ng-input--mono", error && "is-error", className)} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={cx("ng-textarea", className)} />;
}

export function Seg<T extends string>({ options, value, onChange, labels, "aria-label": ariaLabel }: {
  options: readonly T[]; value: T; onChange: (v: T) => void; labels?: Partial<Record<T, string>>; "aria-label"?: string;
}) {
  return (
    <div className="ng-seg" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button key={o} type="button" className={cx("ng-seg__opt", o === value && "is-on")} aria-pressed={o === value} onClick={() => onChange(o)}>
          {labels?.[o] ?? o}
        </button>
      ))}
    </div>
  );
}

export function Toggle({ on, onChange, children }: { on: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className={cx("ng-toggle", on && "is-on")}>
      <input type="checkbox" checked={on} onChange={(e) => onChange(e.target.checked)} hidden />
      <span className="ng-toggle__track" />
      {children}
    </label>
  );
}

/** A number input that commits on blur or Enter. A non-number shows is-error and commits nothing. */
export function NumberField({ value, onCommit, parse = parseNumber, format = String, error: externalError, onValidity, ...rest }:
  Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange"> & {
    value: number | null; onCommit: (n: number) => void;
    parse?: (s: string) => number | null; format?: (n: number) => string; error?: boolean;
    onValidity?: (valid: boolean) => void;
  }) {
  const [text, setText] = useState(value == null ? "" : format(value));
  const [bad, setBad] = useState(false);
  useEffect(() => {
    setText(value == null ? "" : format(value));
    setBad(false);
  }, [value]);
  const commit = () => {
    if (text.trim() === "" && value == null) return;
    const n = parse(text);
    if (n == null) { setBad(true); onValidity?.(false); return; }
    setBad(false);
    onValidity?.(true);
    if (n !== value) onCommit(n);
    else setText(format(n));
  };
  return (
    <Input
      mono
      inputMode="decimal"
      {...rest}
      error={bad || externalError}
      aria-invalid={bad || undefined}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
    />
  );
}

export function parseNumber(s: string): number | null {
  const t = s.trim();
  if (!/^\d+(\.\d+)?$/.test(t)) return null;
  const n = Number(t);
  return n > 0 ? n : null;
}

export function parseMoney(s: string): number | null {
  return parseNumber(s.trim().replace(/^\$/, ""));
}

const KEY_PILL = {
  none: { cls: "ng-pill", glyph: "○", word: "No key" },
  set: { cls: "ng-pill ng-pill--ok", glyph: "✓", word: "Key set" },
  rejected: { cls: "ng-pill ng-pill--danger", glyph: "✕", word: "Key rejected" },
} as const;

/** Write-only secret. Never renders a key; Replace reveals an empty input cleared on save. */
export function KeyField({ label, status, onReplace }: { label: string; status: KeyStatus; onReplace: (value: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const id = useId();
  const pill = KEY_PILL[status.status];
  const note =
    status.status === "rejected" ? status.message ?? "The provider rejected the key."
      : status.status === "set" ? (status.checked_at ? `checked ${status.checked_at.slice(11, 16)}` : "Stored on this machine. It cannot be shown again.")
        : "Nothing stored.";
  if (editing) {
    const save = async () => {
      if (!draft.trim()) return;
      setBusy(true);
      setFailed(null);
      try {
        await onReplace(draft.trim());
        setDraft("");
        setEditing(false);
      } catch {
        // Never echo the key or the server's text back: it may contain the key.
        setFailed("Not saved: Netgrip did not store the key. Try again.");
      } finally {
        setBusy(false);
      }
    };
    return (
      <div className="ng-row">
        <Input mono id={id} aria-label={label} className="ng-grow" type="password" autoComplete="off" value={draft}
          onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void save(); }} autoFocus />
        <Button size="sm" onClick={save} sent={busy} sentLabel="Saving…" disabled={!draft.trim()}>Save key</Button>
        <Button size="sm" variant="quiet" onClick={() => { setDraft(""); setFailed(null); setEditing(false); }}>Cancel</Button>
        {failed && <span className="ng-field__hint is-error">{failed}</span>}
      </div>
    );
  }
  return (
    <div className="ng-keyfield">
      <span className={pill.cls}><i>{pill.glyph}</i>{pill.word}</span>
      <span className="ng-mono ng-faint ng-grow">{note}</span>
      <Button size="sm" onClick={() => setEditing(true)}>Replace</Button>
    </div>
  );
}
