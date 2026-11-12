import { useId } from "react";
import { Field, Textarea } from "../ui/Field";

export const PROMPT_HINT = "Kept word for word. Anything you assume here is checked first, and you are told if it is wrong.";

/** The prompt field from ScreenNewInvestigation: textarea at 15/22. */
export function PromptBox({ value, onChange, autoFocus }: { value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  const id = useId();
  return (
    <Field label="Your question or claim" htmlFor={id} hint={PROMPT_HINT}>
      <Textarea id={id} className="prompt-box" value={value} autoFocus={autoFocus} onChange={(e) => onChange(e.target.value)} />
    </Field>
  );
}
