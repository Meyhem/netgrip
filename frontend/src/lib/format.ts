export const money = (n: number) => `$${n.toFixed(2)}`;
export const moneyOf = (a: number, b: number) => `${money(a)} / ${money(b)}`;

export function duration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** Run time as h:mm:ss: "0:22:10". */
export function clock(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds));
  return `${Math.floor(t / 3600)}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

const MB = 1024 * 1024;
export function bytes(n: number): string {
  if (n <= 0) return "0 MB";
  const mb = n / MB;
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  if (mb >= 10) return `${Math.round(mb)} MB`;
  return `${Math.max(0.1, Math.round(mb * 10) / 10)} MB`;
}

/** Time in a run, short: "2:41", or "1:02:41" past an hour. */
export function elapsed(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds));
  return t >= 3600 ? clock(t) : `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

/** Local time of day as "13:58". */
export function timeOfDay(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}
