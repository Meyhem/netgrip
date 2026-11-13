import { useEffect, useRef, useState } from "react";
import { conclusionLike } from "../lib/conclusionLike";
import { Button } from "./Button";
import { cx } from "./cx";

export interface ComposerTarget {
  id: string;
  display_id: string;
  /** What follows the id in the head: the node's question, or "the whole investigation". */
  label: string;
}

export interface InstructionComposerProps {
  target: ComposerTarget;
  /** Nodes the instruction reaches: the target and all its descendants (U1). */
  reach: number;
  hasChildren: boolean;
  /** No text: the root after approval, or an investigation that is no longer steerable. A
   * string replaces the root's explanation. */
  locked?: boolean | string;
  /** Changes when `I` was pressed: the field takes focus. */
  focusToken?: number;
  /** Plan review: every instruction redraws the whole plan. */
  plan?: boolean;
  buttonLabel: string;
  buttonVariant?: "default" | "steer";
  /** Returns false when the instruction was not sent; the draft is then kept. */
  onSend: (text: string) => boolean | void | Promise<boolean | void>;
  sent?: boolean;
  sentLabel?: string;
  disabled?: boolean;
  /** Scopes the saved draft (e.g. the investigation id); drafts are kept per node. */
  draftKey?: string;
}

const CONCLUSION_WARNING = "You can change what is investigated, not what is concluded. Netgrip will check this as a hypothesis.";
const LOCKED = "The root goal cannot be re-planned once research is running. Instruct a branch, or stop and start a new investigation.";

const storageKey = (scope: string | undefined, nodeId: string) => `netgrip.draft.${scope ?? ""}.${nodeId}`;

function readDraft(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeDraft(key: string, text: string) {
  try {
    if (text) sessionStorage.setItem(key, text);
    else sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable: the draft lives only in the field */
  }
}

/** Where the user steers with words: head with target and reach, the textarea, and a foot that
 * says when the instruction takes effect. `⌘↵` sends; `Esc` leaves the field and keeps the draft. */
export function InstructionComposer({
  target, reach, hasChildren, locked, focusToken, plan, buttonLabel, buttonVariant = "default",
  onSend, sent, sentLabel, disabled, draftKey,
}: InstructionComposerProps) {
  const key = storageKey(draftKey, target.id);
  const [text, setText] = useState(() => readDraft(key));
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => setText(readDraft(key)), [key]);
  useEffect(() => { if (focusToken) box.current?.focus(); }, [focusToken]);

  const change = (value: string) => {
    setText(value);
    writeDraft(key, value);
  };

  if (locked) {
    return (
      <div className="ng-composer is-locked">
        <div className="ng-composer__head">✎︎ Instruct {target.display_id} <span>· {target.label}</span></div>
        <div className="ng-composer__foot"><span className="ng-grow">{typeof locked === "string" ? locked : LOCKED}</span></div>
      </div>
    );
  }

  const warn = conclusionLike(text);
  const canSend = text.trim() !== "" && !sent && !disabled;
  const send = async () => {
    if (!canSend) return;
    const sending = text;
    const ok = await onSend(sending.trim());
    if (ok !== false) {
      writeDraft(key, "");
      setText((t) => (t === sending ? "" : t));
    }
  };

  const foot = warn
    ? CONCLUSION_WARNING
    : plan
      ? "The plan is redrawn each time. You can change what is investigated, not what is concluded."
      : hasChildren
        ? `Takes effect at each node's next step. ${target.display_id} will re-plan its children.`
        : "Takes effect at the node's next step.";

  return (
    <div className="ng-composer">
      <div className="ng-composer__head">
        ✎︎ Instruct {target.display_id} <span>· {target.label} · reaches {reach} {reach === 1 ? "node" : "nodes"}</span>
      </div>
      <textarea
        ref={box}
        aria-label={`Instruction for ${target.display_id}`}
        placeholder={plan ? "Leave out a line of inquiry, add one, narrow the scope…" : "Narrow the scope, add a line of inquiry, prefer a kind of source…"}
        value={text}
        onChange={(e) => change(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void send();
          } else if (e.key === "Escape") {
            box.current?.blur();
          }
        }}
      />
      <div className="ng-composer__foot">
        <span className={cx("ng-grow", warn && "ng-warn")}>{foot}</span>
        <span className="ng-kbd">⌘↵</span>
        <Button size="sm" variant={buttonVariant} onClick={() => void send()} disabled={!canSend} sent={sent} sentLabel={sentLabel}>
          {warn ? `${buttonLabel} anyway` : buttonLabel}
        </Button>
      </div>
    </div>
  );
}
