import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, sendCommand, getJSON } from "./client";

afterEach(() => vi.unstubAllGlobals());

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("api client", () => {
  it("sendCommand retries with the same id after a network error", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(json(202, { recorded: true, duplicate: false }));
    vi.stubGlobal("fetch", fetchMock);
    const ack = await sendCommand("inv-1", "pause", { retryDelayMs: 0 });
    expect(ack).toEqual({ recorded: true, duplicate: false });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const ids = fetchMock.mock.calls.map((c) => JSON.parse(c[1].body).id);
    expect(new Set(ids).size).toBe(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/investigations/inv-1/commands");
  });

  it("409 becomes ApiError with code", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(409, { code: "not_allowed", message: "Nothing is paused" })));
    const err = await sendCommand("inv-1", "resume").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "not_allowed", message: "Nothing is paused" });
  });

  it("getJSON throws ApiError on 404", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(404, { detail: "No such investigation" })));
    await expect(getJSON("/api/investigations/x")).rejects.toMatchObject({ status: 404, message: "No such investigation" });
  });
});
