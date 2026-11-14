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
      current = { ...current, ...partial, presets: Object.fromEntries(Object.entries(current.presets).map(([k, v]) => [k, { ...v, ...(partial.presets?.[k] ?? {}) }])) as typeof current.presets, effort: { ...current.effort, ...Object.fromEntries(Object.entries(partial.effort ?? {}).map(([k, v]) => [k, { ...current.effort[k as "Low"], ...(v as object) }])) } };
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
  it("changing Medium max nodes sends PATCH with only that field", { timeout: 15_000 }, async () => {
    const f = api();
    show();
    // Under a loaded full-suite run the default 1 s waits were too short (an intermittent
    // failure). "Saved" stays 2 s; waitFor also checks on every DOM change, so it sees it.
    const slow = { timeout: 5000 };
    const input = await screen.findByLabelText("Medium max nodes", {}, slow);
    expect(input).toHaveValue("40");
    fireEvent.change(input, { target: { value: "50" } });
    fireEvent.blur(input);
    await waitFor(() => expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(1), slow);
    expect(JSON.parse(callsTo(f, "PATCH", "/api/settings")[0][1]!.body as string)).toEqual({ effort: { Medium: { max_nodes: 50 } } });
    expect(await screen.findByText("Saved", {}, slow)).toBeInTheDocument();
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
    expect(screen.getByText("now: 4 open · 2 restarts today · 7 fetches timed out")).toBeInTheDocument();
  });

  it("no theme, account or notification section exists", async () => {
    api();
    show();
    await screen.findByText("Key set");
    const ids = Array.from(document.querySelectorAll("section")).map((s) => s.id);
    expect(ids).toEqual(["keys", "models", "effort", "spend", "sources", "capacity", "storage"]);
    expect(screen.queryByText(/theme|account|notification/i)).toBeNull();
  });

  describe("model pickers", () => {
    const OFFER = [
      { id: "anthropic/claude-opus-5.5", name: "Anthropic: Claude Opus 5.5", price_in_per_m: 15, price_out_per_m: 75, context_length: 1_000_000 },
      { id: "meta-llama/llama-4-maverick", name: "Meta: Llama 4 Maverick", price_in_per_m: 0.2, price_out_per_m: 0.6, context_length: 128_000 },
      { id: "mistralai/mistral-large", name: "Mistral Large", price_in_per_m: 2, price_out_per_m: 6, context_length: 128_000 },
    ];
    const body = (f: ReturnType<typeof api>, i = 0) => JSON.parse(callsTo(f, "PATCH", "/api/settings")[i][1]!.body as string);
    const options = () => within(screen.getByRole("listbox")).queryAllByRole("option").map((o) => o.querySelector("b")!.textContent);

    it("typing searches the provider's models fuzzily and Enter picks one with its price", async () => {
      const f = api({ "GET /api/settings/models/available": OFFER });
      show();
      const pick = await screen.findByRole("combobox", { name: "Balanced Fast model" });
      await waitFor(() => expect(screen.getByRole("combobox", { name: "Add a model" })).not.toBeDisabled());
      fireEvent.focus(pick);
      fireEvent.change(pick, { target: { value: "llmav" } });
      expect(options()[0]).toBe("meta-llama/llama-4-maverick");
      expect(within(screen.getByRole("listbox")).getAllByRole("option")[0]).toHaveTextContent("$0.20 / $0.60");
      fireEvent.keyDown(pick, { key: "Enter" });
      await waitFor(() => expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(1));
      expect(body(f).presets).toEqual({ balanced: { fast: "meta-llama/llama-4-maverick" } });
      expect(body(f).models.at(-1)).toEqual({ id: "meta-llama/llama-4-maverick", price_in_per_m: 0.2, price_out_per_m: 0.6, price_source: "provider" });
    });

    it("the search matches model names and says when nothing matches", async () => {
      api({ "GET /api/settings/models/available": OFFER });
      show();
      const pick = await screen.findByRole("combobox", { name: "Balanced Strong model" });
      await waitFor(() => expect(screen.getByRole("combobox", { name: "Add a model" })).not.toBeDisabled());
      fireEvent.focus(pick);
      fireEvent.change(pick, { target: { value: "large mistral" } });
      expect(options()).toEqual(["mistralai/mistral-large"]);
      fireEvent.change(pick, { target: { value: "qqqq" } });
      expect(screen.getByText(/No model matches/)).toBeInTheDocument();
    });

    it("Escape puts the saved value back and sends nothing", async () => {
      const f = api({ "GET /api/settings/models/available": OFFER });
      show();
      const pick = await screen.findByRole("combobox", { name: "Balanced Fast model" });
      const before = (pick as HTMLInputElement).value;
      fireEvent.focus(pick);
      fireEvent.change(pick, { target: { value: "mistral" } });
      fireEvent.keyDown(pick, { key: "Escape" });
      expect(pick).toHaveValue(before);
      expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(0);
    });

    it("Add a model offers only models not yet listed", async () => {
      const f = api({ "GET /api/settings/models/available": OFFER });
      show();
      const add = await screen.findByRole("combobox", { name: "Add a model" });
      await waitFor(() => expect(add).not.toBeDisabled());
      fireEvent.focus(add);
      expect(options()).not.toContain("anthropic/claude-opus-5.5");
      fireEvent.mouseDown(screen.getByRole("option", { name: /mistral-large/ }));
      await waitFor(() => expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(1));
      expect(body(f).models).toHaveLength(settings().models.length + 1);
    });

    it("without the provider's list the pickers still offer the listed models", async () => {
      api();
      show();
      const pick = await screen.findByRole("combobox", { name: "Balanced Fast model" });
      fireEvent.focus(pick);
      expect(options()).toHaveLength(settings().models.length);
      expect(screen.getByRole("combobox", { name: "Add a model" })).toBeDisabled();
    });
  });

  describe("provider routing", () => {
    it("picking lowest price sends only the routing sort", async () => {
      const f = api();
      show();
      const sort = await screen.findByLabelText("Provider routing");
      fireEvent.change(sort, { target: { value: "price" } });
      await waitFor(() => expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(1));
      expect(JSON.parse(callsTo(f, "PATCH", "/api/settings")[0][1]!.body as string)).toEqual({ model_routing: { sort: "price" } });
    });

    it("the data policy toggles send their own flag", async () => {
      const f = api();
      show();
      fireEvent.click(await screen.findByText("Only providers with zero data retention"));
      await waitFor(() => expect(callsTo(f, "PATCH", "/api/settings")).toHaveLength(1));
      expect(JSON.parse(callsTo(f, "PATCH", "/api/settings")[0][1]!.body as string)).toEqual({ model_routing: { zero_retention: true } });
    });

    it("is disabled for endpoints other than OpenRouter", async () => {
      api({ "GET /api/settings": settings({ model_endpoint: "http://localhost:11434/v1" }) });
      show();
      expect(await screen.findByLabelText("Provider routing")).toBeDisabled();
      expect(screen.getByText(/Only OpenRouter routes between providers/)).toBeInTheDocument();
    });
  });
});
