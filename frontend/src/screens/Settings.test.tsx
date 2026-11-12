import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { callsTo, mockApi } from "../test/fetch";
import { POOLS, settings } from "../test/fixtures";

afterEach(() => vi.unstubAllGlobals());

function api(extra: Record<string, unknown> = {}) {
  let current = settings();
  return mockApi({
    "GET /api/settings": () => current,
    "PATCH /api/settings": (_u: string, init: RequestInit) => {
      const partial = JSON.parse(init.body as string);
      current = { ...current, ...partial, effort: { ...current.effort, ...Object.fromEntries(Object.entries(partial.effort ?? {}).map(([k, v]) => [k, { ...current.effort[k as "Low"], ...(v as object) }])) } };
      return current;
    },
    "PUT /api/settings/keys/model": { set: true, status: "set", checked_at: null, message: null },
    "GET /api/system/pools": POOLS,
    "GET /api/system/storage": { total_bytes: 387 * 1024 * 1024, investigations: 6, pages: 1204, data_dir: "/home/u/netgrip/data" },
    "POST /api/system/rebuild": { replayed: 419 },
    ...extra,
  });
}

const show = () => render(<MemoryRouter><Settings /></MemoryRouter>);

describe("Settings", () => {
  it("changing Medium max nodes sends PATCH with only that field", async () => {
    const f = api();
    show();
    const input = await screen.findByLabelText("Medium max nodes");
    expect(input).toHaveValue("40");
    fireEvent.change(input, { target: { value: "50" } });
    fireEvent.blur(input);
    await waitFor(() => expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(1));
    expect(JSON.parse(callsTo(f, "PATCH", "/api/settings")[0][1]!.body as string)).toEqual({ effort: { Medium: { max_nodes: 50 } } });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("non-numeric input shows is-error and sends nothing", async () => {
    const f = api();
    show();
    const input = await screen.findByLabelText("Medium max nodes");
    fireEvent.change(input, { target: { value: "forty" } });
    fireEvent.blur(input);
    expect(input).toHaveClass("is-error");
    expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(0);
  });

  it("key row shows status words and never an input value from the server", async () => {
    api({
      "GET /api/settings": settings({
        keys: {
          model: { set: true, status: "set", checked_at: null, message: null },
          search: { set: true, status: "rejected", checked_at: "2026-11-12T02:14:00Z", message: 'Tavily answered "invalid key"' },
        },
      }),
    });
    const { container } = show();
    expect(await screen.findByText("Key set")).toBeInTheDocument();
    expect(screen.getByText("Key rejected")).toHaveClass("ng-pill--danger");
    expect(screen.getByText('Tavily answered "invalid key"')).toBeInTheDocument();
    const keys = container.querySelector("#keys")!;
    expect(keys.querySelectorAll('input[type="password"]')).toHaveLength(0);
    expect(within(keys as HTMLElement).getAllByRole("button", { name: "Replace" })).toHaveLength(2);
  });

  it("Replace sends PUT and clears the input", async () => {
    const f = api();
    show();
    const keys = (await screen.findByText("Model provider")).closest("section")!;
    fireEvent.click(within(keys).getAllByRole("button", { name: "Replace" })[0]);
    const input = within(keys).getByLabelText("Model provider key");
    fireEvent.change(input, { target: { value: "sk-or-test-123" } });
    fireEvent.click(within(keys).getByRole("button", { name: "Save key" }));
    await waitFor(() => expect(callsTo(f, "PUT", "/api/settings/keys/model")).toHaveLength(1));
    expect(JSON.parse(callsTo(f, "PUT", "/api/settings/keys/model")[0][1]!.body as string)).toEqual({ value: "sk-or-test-123" });
    await waitFor(() => expect(within(keys).queryByLabelText("Model provider key")).toBeNull());
    expect(document.body.innerHTML).not.toContain("sk-or-test-123");
  });

  it("rebuild shows the event count", async () => {
    api();
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Rebuild state from history" }));
    expect(await screen.findByText("Rebuilt from 419 events.")).toBeInTheDocument();
  });

  it("a model with no price has empty is-error price inputs and a warn note", async () => {
    api();
    show();
    const input = await screen.findByLabelText("openai/gpt-5.2 input price");
    expect(input).toHaveValue("");
    expect(input).toHaveClass("is-error");
    expect(screen.getByText(/No price on record/)).toHaveClass("ng-warn");
  });

  it("capacity shows what is in use now", async () => {
    api();
    show();
    expect(await screen.findByText("now: 5 in use")).toHaveClass("ng-mono");
    expect(screen.getByText("now: 4 open")).toBeInTheDocument();
  });

  it("no theme, account or notification section exists", async () => {
    api();
    show();
    await screen.findByText("Key set");
    const ids = Array.from(document.querySelectorAll("section")).map((s) => s.id);
    expect(ids).toEqual(["keys", "models", "effort", "spend", "sources", "capacity", "storage"]);
    expect(screen.queryByText(/theme|account|notification/i)).toBeNull();
  });
});
