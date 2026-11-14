import { useId, useMemo, useRef, useState, type ReactNode } from "react";
import type { OfferedModel } from "../api/types";
import { rank } from "../lib/fuzzy";

/** A model the picker can offer: from the provider's list, or already listed in Settings. */
export type PickableModel = Pick<OfferedModel, "id"> & Partial<Omit<OfferedModel, "id">>;

function Marked({ text, marks }: { text: string; marks: number[] }) {
  if (!marks.length) return <>{text}</>;
  const set = new Set(marks);
  const out: ReactNode[] = [];
  let run = "";
  let on = false;
  const flush = (k: number) => { if (run) out.push(on ? <mark key={k}>{run}</mark> : run); run = ""; };
  [...text].forEach((ch, i) => {
    if (set.has(i) !== on) { flush(i); on = set.has(i); }
    run += ch;
  });
  flush(text.length);
  return <>{out}</>;
}

const perM = (n: number) => `$${n < 1 ? n.toFixed(2) : n.toFixed(n % 1 ? 2 : 0)}`;
const priceText = (m: PickableModel) =>
  m.price_in_per_m != null && m.price_out_per_m != null ? `${perM(m.price_in_per_m)} / ${perM(m.price_out_per_m)}` : "no price";
const context = (n?: number | null) => (n ? ` · ${n >= 1_000_000 ? `${n / 1_000_000}M` : `${Math.round(n / 1000)}k`} context` : "");

/** `ng-combo`: a searchable model picker (design-system Field README). Typing filters by fuzzy
 * match over id and name; arrows move, Enter picks, Escape puts the saved value back. */
export function ModelCombo({ label, value, models, onPick, placeholder, disabled }: {
  label: string; value: string; models: PickableModel[]; onPick: (id: string) => void; placeholder?: string; disabled?: boolean;
}) {
  const [query, setQuery] = useState<string | null>(null); // null: not searching, show the value
  const [hover, setHover] = useState(0);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);
  const open = query != null;
  const hits = useMemo(
    () => (open ? rank(models, query, (m) => [m.id, m.name ?? ""]) : []),
    [open, models, query],
  );

  const close = () => { setQuery(null); setHover(0); };
  const pick = (id: string) => {
    close();
    if (id !== value) onPick(id);
  };

  return (
    <div className="ng-combo">
      <input ref={input} className="ng-input ng-input--mono" role="combobox" aria-label={label} aria-expanded={open}
        aria-controls={listId} aria-autocomplete="list" disabled={disabled} placeholder={placeholder}
        aria-activedescendant={open && hits[hover] ? `${listId}-${hover}` : undefined}
        value={query ?? value} title={value || undefined} spellCheck={false} autoComplete="off"
        onFocus={(e) => { setQuery(""); e.currentTarget.select(); }}
        onBlur={close}
        onChange={(e) => { setQuery(e.target.value); setHover(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); if (!open) setQuery(""); else setHover((h) => Math.min(h + 1, hits.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setHover((h) => Math.max(h - 1, 0)); }
          else if (e.key === "Enter" && open) { e.preventDefault(); if (hits[hover]) { pick(hits[hover].item.id); input.current?.blur(); } }
          else if (e.key === "Escape" && open) { e.preventDefault(); close(); input.current?.blur(); }
        }} />
      {open && (
        <ul className="ng-menu ng-combo__list" role="listbox" id={listId} aria-label={label}>
          {hits.length === 0 && <li className="ng-combo__empty">No model matches “{query}”.</li>}
          {hits.map(({ item: m, marks }, i) => (
            <li key={m.id} id={`${listId}-${i}`} role="option" aria-selected={m.id === value}
              className={`ng-menu__item${i === hover ? " is-hover" : ""}`}
              ref={i === hover ? (el) => el?.scrollIntoView?.({ block: "nearest" }) : undefined}
              onMouseEnter={() => setHover(i)}
              onMouseDown={(e) => { e.preventDefault(); pick(m.id); input.current?.blur(); }}>
              <b><Marked text={m.id} marks={marks[0]} /></b>
              <span>{priceText(m)}</span>
              {(m.name || m.context_length) && <small><Marked text={m.name ?? ""} marks={marks[1] ?? []} />{context(m.context_length)}</small>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
