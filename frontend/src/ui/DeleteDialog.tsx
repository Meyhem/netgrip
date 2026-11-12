import { useEffect, useState } from "react";
import { bytes } from "../lib/format";
import { Button } from "./Button";

/** The app's only modal, on scrim. Deleting cannot be undone. */
export function DeleteDialog({ prompt, diskBytes, onCancel, onDelete }: {
  prompt: string; diskBytes: number; onCancel: () => void; onDelete: () => Promise<void>;
}) {
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  const del = async () => {
    setSent(true);
    setFailed(null);
    try {
      await onDelete();
    } catch (e) {
      setSent(false);
      setFailed(e instanceof Error ? e.message : "The investigation was not deleted.");
    }
  };
  return (
    <div className="scrim" onClick={onCancel}>
      <div className="ng-panel dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title" onClick={(e) => e.stopPropagation()}>
        <div className="ng-panel__head"><span id="delete-title" className="ng-heading">Delete investigation</span></div>
        <div className="ng-panel__body ng-col ng-col--loose">
          <p className="ng-clip ng-heading" title={prompt}>{prompt}</p>
          <p className="ng-small">
            Deletes its plan, events, claims and report. Frees <span className="ng-mono">{bytes(diskBytes)}</span>. This cannot be undone.
          </p>
          {failed && <p className="ng-small ng-danger">{failed}</p>}
          <div className="ng-row">
            <Button variant="quiet" className="ng-right" onClick={onCancel}>Cancel</Button>
            <Button variant="danger" onClick={del} sent={sent} sentLabel="Deleting…" autoFocus>Delete investigation</Button>
          </div>
        </div>
      </div>
    </div>
  );
}
