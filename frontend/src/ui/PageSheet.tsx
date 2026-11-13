import { useEffect, useRef, useState } from "react";
import { ApiError, getJSON } from "../api/client";
import { timeOfDaySeconds } from "../lib/format";
import { Banner } from "./Banner";

/** `GET /api/investigations/{id}/pages/{page_version_id}`: the clean text this investigation used. */
export interface StoredPage { url: string; title: string | null; fetched_at: string; text: string }

function fetchedAt(iso: string): string {
  const d = new Date(iso);
  const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `${day} ${timeOfDaySeconds(iso)}`;
}

type Load = { state: "loading" } | { state: "ready"; page: StoredPage } | { state: "missing" } | { state: "error" };

/** A stored page version as inert text, in a full-height sheet over the inspector. The text is a
 * plain text node: no markup is parsed, no links are followed, no scripts or images load.
 * Escape or Close dismisses it, and focus returns to the control that opened it. */
export function PageSheet({ investigationId, pageVersionId, onClose }: {
  investigationId: string; pageVersionId: string; onClose: () => void;
}) {
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    setLoad({ state: "loading" });
    getJSON<StoredPage>(`/api/investigations/${encodeURIComponent(investigationId)}/pages/${encodeURIComponent(pageVersionId)}`).then(
      (page) => { if (live) setLoad({ state: "ready", page }); },
      (e) => { if (live) setLoad(e instanceof ApiError && e.status === 404 ? { state: "missing" } : { state: "error" }); },
    );
    return () => { live = false; };
  }, [investigationId, pageVersionId]);

  // Focus moves into the sheet and returns to the opener when it closes.
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const page = load.state === "ready" ? load.page : null;
  return (
    <section className="page-sheet" role="dialog" aria-label="Stored page">
      <div className="ng-panel__head">
        <span className="ng-label">Stored page</span>
        <button ref={closeRef} type="button" className="ng-btn ng-btn--quiet ng-btn--sm ng-right" aria-label="Close stored page" onClick={onClose}>Close</button>
      </div>
      <div className="ng-pane__scroll ng-col page-sheet__body">
        {load.state === "loading" && (
          <div className="ng-activity"><span className="ng-activity__verb">Loading</span><span className="ng-activity__what">Stored page</span></div>
        )}
        {load.state === "missing" && (
          <Banner tone="warn" title="This stored page is not available.">Its text is no longer in storage.</Banner>
        )}
        {load.state === "error" && (
          <Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner>
        )}
        {page && (
          <>
            <div className="ng-col page-sheet__meta">
              {page.title && <h3 className="ng-heading">{page.title}</h3>}
              <span className="ng-mono ng-muted page-sheet__url">{page.url}</span>
              <span className="ng-mono ng-faint">fetched {fetchedAt(page.fetched_at)}</span>
            </div>
            <pre className="ng-small page-sheet__text">{page.text}</pre>
          </>
        )}
      </div>
    </section>
  );
}
