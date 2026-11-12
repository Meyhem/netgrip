import type { CommandAck, InvestigationSettings } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    const message = body?.message ?? (typeof detail === "string" ? detail : res.statusText || "Request failed");
    throw new ApiError(res.status, body?.code ?? (res.status === 422 ? "invalid" : String(res.status)), message);
  }
  return body as T;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body !== undefined) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(body);
  }
  return parse<T>(await fetch(path, init));
}

export const getJSON = <T>(path: string) => request<T>("GET", path);
export const patchJSON = <T>(path: string, body: unknown) => request<T>("PATCH", path, body);
export const putJSON = <T>(path: string, body: unknown) => request<T>("PUT", path, body);
export const postJSON = <T>(path: string, body: unknown = {}) => request<T>("POST", path, body);

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** POST with one id for every attempt: a network error is retried (up to 3 times) with the
 * same id, so the server records the command at most once. HTTP errors are not retried. */
async function idempotentPost<T>(path: string, body: unknown, retryDelayMs = 300): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= 3; attempt++) {
    if (attempt > 0) await sleep(retryDelayMs * attempt);
    let res: Response;
    try {
      res = await fetch(path, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (e) {
      lastError = e;
      continue;
    }
    return parse<T>(res);
  }
  throw lastError;
}

export interface CommandOptions {
  nodeId?: string | null;
  payload?: Record<string, unknown>;
  id?: string;
  retryDelayMs?: number;
}

export function sendCommand(investigationId: string, type: string, opts: CommandOptions = {}): Promise<CommandAck> {
  const body = { id: opts.id ?? crypto.randomUUID(), type, node_id: opts.nodeId ?? null, payload: opts.payload ?? {} };
  return idempotentPost(`/api/investigations/${encodeURIComponent(investigationId)}/commands`, body, opts.retryDelayMs);
}

export function createInvestigation(
  id: string,
  prompt: string,
  settings: Partial<InvestigationSettings>,
  retryDelayMs?: number,
): Promise<CommandAck> {
  return idempotentPost("/api/investigations", { id, prompt, settings }, retryDelayMs);
}

export function deleteInvestigation(id: string): Promise<void> {
  return request<void>("DELETE", `/api/investigations/${encodeURIComponent(id)}`);
}
