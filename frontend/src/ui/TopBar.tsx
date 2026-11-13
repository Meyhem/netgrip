import { NavLink, useLocation } from "react-router-dom";
import { getJSON } from "../api/client";
import type { Pools } from "../api/types";
import { money } from "../lib/format";
import { usePoll } from "../lib/usePoll";

export function poolsText(p: Pools): string {
  return `models ${p.models.in_use}/${p.models.limit} · search ${p.search.in_use}/${p.search.limit} · browsers ${p.browsers.in_use}/${p.browsers.limit} · today ${money(p.today_usd)}`;
}

/** "4 open · 2 restarts today · 7 fetches timed out": what the browser pool has been doing. */
export function browserHealthText(b: Pools["browsers"]): string {
  const restarts = b.restarts_today ?? 0;
  const timedOut = b.timed_out_today ?? 0;
  return `${b.in_use} open · ${restarts} restart${restarts === 1 ? "" : "s"} today · ${timedOut} fetch${timedOut === 1 ? "" : "es"} timed out`;
}

export function TopBar() {
  const { data: pools } = usePoll(() => getJSON<Pools>("/api/system/pools"), 5000);
  const { pathname } = useLocation();
  const onSettings = pathname.startsWith("/settings");
  return (
    <header className="ng-top">
      <span className="ng-brand">net<i>grip</i></span>
      <nav className="ng-nav">
        <NavLink to="/" className={onSettings ? "" : "is-on"}>Investigations</NavLink>
        <NavLink to="/settings" className={onSettings ? "is-on" : ""}>Settings</NavLink>
      </nav>
      {pools && (
        <div className="ng-pools" aria-label={poolsText(pools)} title={`${poolsText(pools)} — browsers: ${browserHealthText(pools.browsers)}`}>
          <span>models <b>{pools.models.in_use}</b>/{pools.models.limit}</span>
          <span>search <b>{pools.search.in_use}</b>/{pools.search.limit}</span>
          <span>browsers <b>{pools.browsers.in_use}</b>/{pools.browsers.limit}</span>
          <span>today <b>{money(pools.today_usd)}</b></span>
        </div>
      )}
    </header>
  );
}
