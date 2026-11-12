import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { openStream } from "./stream";
import { FakeEventSource } from "../test/eventSource";

beforeEach(() => {
  FakeEventSource.reset();
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const ev = (seq: number) => ({ seq, investigation_id: "inv-1", type: "x", v: 1, at: "", actor: "user", node_id: null, command_id: null, data: {} });

describe("openStream", () => {
  it("stream reconnects from the last seq and reports \"reconnecting\"", () => {
    const onDurable = vi.fn(), onEphemeral = vi.fn(), onStatus = vi.fn();
    const close = openStream("inv-1", 7, { onDurable, onEphemeral, onStatus }, { backoffMs: 500 });
    const first = FakeEventSource.last;
    expect(first.url).toBe("/api/investigations/inv-1/stream?after=7");
    first.open();
    expect(onStatus).toHaveBeenLastCalledWith("open");
    first.durable(ev(8));
    first.durable(ev(9));
    first.ephemeral({ investigation_id: "inv-1", node_id: null, kind: "text", data: { t: "a" } });
    expect(onDurable.mock.calls.map(([e]) => e.seq)).toEqual([8, 9]);
    expect(onEphemeral).toHaveBeenCalledWith({ investigation_id: "inv-1", node_id: null, kind: "text", data: { t: "a" } });

    first.fail();
    expect(first.closed).toBe(true);
    expect(onStatus).toHaveBeenLastCalledWith("reconnecting");
    expect(FakeEventSource.instances).toHaveLength(1);
    vi.advanceTimersByTime(500);
    const second = FakeEventSource.last;
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(second.url).toBe("/api/investigations/inv-1/stream?after=9");
    second.open();
    expect(onStatus).toHaveBeenLastCalledWith("open");

    close();
    expect(second.closed).toBe(true);
  });

  it("closing while waiting to reconnect opens nothing more", () => {
    const close = openStream("inv-1", 0, { onDurable: vi.fn(), onEphemeral: vi.fn(), onStatus: vi.fn() }, { backoffMs: 100 });
    FakeEventSource.last.fail();
    close();
    vi.advanceTimersByTime(1000);
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});
