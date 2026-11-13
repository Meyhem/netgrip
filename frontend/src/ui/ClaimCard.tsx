import type { Claim, ClaimSource, Credibility } from "../api/types";
import { ClaimStatus } from "./ClaimStatus";
import { cx } from "./cx";

const CREDIBILITY_TAG: Record<Credibility, string> = { Primary: "ng-tag ng-tag--solid", Reputable: "ng-tag", Weak: "ng-tag ng-tag--dashed" };

/** Host and path, without the scheme: "nasa.gov/vision/…". */
export const shortUrl = (url: string) => url.replace(/^[a-z]+:\/\//i, "").replace(/^www\./, "");

/** Sources by origin: independence is by origin, not by page (V2). */
export const independent = (sources: ClaimSource[]) => new Set(sources.map((s) => s.origin_key)).size;

function Source({ source, against }: { source: ClaimSource; against?: boolean }) {
  const lost = !source.page_version_id;
  return (
    <div className={cx("ng-src", against && "ng-src--against", lost && "ng-src--lost")}>
      {lost ? <span className="ng-tag ng-tag--dashed">LOST</span> : <span className={CREDIBILITY_TAG[source.credibility]}>{source.credibility.toUpperCase()}</span>}
      <span className="ng-src__url" title={source.url}>{shortUrl(source.url)}</span>
      <span>{lost ? "unobtainable" : source.published_at?.slice(0, 10) ?? ""}</span>
    </div>
  );
}

function supportsLabel(sources: ClaimSource[]): string {
  const n = independent(sources);
  return sources.length > n ? `Supports · ${n} independent · ${sources.length} pages` : `Supports · ${n} independent`;
}

/** One claim: its status, its text and the sources for and against it. Text is data: shown as
 * characters only. `compact` is the Overview's "claims so far" form, without sources. */
export function ClaimCard({ claim, nodeDisplayIds, compact }: { claim: Claim; nodeDisplayIds: Record<string, string>; compact?: boolean }) {
  const from = claim.node_id ? nodeDisplayIds[claim.node_id] : undefined;
  const head = (
    <div className="ng-row">
      <ClaimStatus status={claim.status} />
      <span className="ng-mono ng-faint ng-right">{from ? `${claim.id} · from ${from}` : claim.id}</span>
    </div>
  );
  if (compact) {
    return <div className="ng-claim inspector__claim">{head}<span className="ng-small">{claim.text}</span></div>;
  }
  return (
    <div className="ng-claim">
      {head}
      <div className="ng-claim__text">{claim.text}</div>
      {(claim.supporting.length > 0 || claim.contradicting.length > 0) && (
        <div className="ng-col claim-card__sources">
          {claim.supporting.length > 0 && <span className="ng-label">{supportsLabel(claim.supporting)}</span>}
          {claim.supporting.map((s) => <Source key={s.id} source={s} />)}
          {claim.contradicting.length > 0 && <span className="ng-label">Contradicts · {claim.contradicting.length}</span>}
          {claim.contradicting.map((s) => <Source key={s.id} source={s} against />)}
        </div>
      )}
    </div>
  );
}
