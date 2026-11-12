import { vi } from "vitest";

type Handler = (url: string, init: RequestInit) => unknown | Promise<unknown>;

/** Stub fetch with handlers keyed by "METHOD /path" (a `*` segment matches any one segment).
 * A handler may return a Response, or a value that is sent as 200 JSON. Unknown routes answer 404. */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const path = url.split("?")[0];
    const key = `${init.method ?? "GET"} ${path}`;
    const match = key in routes ? key : Object.keys(routes).find((k) => k.includes("*") && matches(k, key));
    if (match === undefined) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    const r = routes[match];
    const value = typeof r === "function" ? await (r as Handler)(url, init) : r;
    if (value instanceof Response) return value;
    return new Response(JSON.stringify(value ?? null), { status: 200, headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function matches(pattern: string, key: string): boolean {
  const p = pattern.split("/");
  const k = key.split("/");
  return p.length === k.length && p.every((seg, i) => seg === "*" || seg === k[i]);
}

export const callsTo = (fn: ReturnType<typeof mockApi>, method: string, path: string) =>
  fn.mock.calls.filter(([u, i]) => String(u).split("?")[0] === path && ((i as RequestInit | undefined)?.method ?? "GET") === method);
