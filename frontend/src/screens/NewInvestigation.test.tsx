import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NewInvestigation } from "./NewInvestigation";
import { callsTo, mockApi } from "../test/fetch";
import { row, settings } from "../test/fixtures";
import type { Settings } from "../api/types";

afterEach(() => vi.unstubAllGlobals());

const EST = {
  low_usd: 1.6, high_usd: 4.2, unpriced_models: [] as string[],
  per_tier: {
    strong: { low_usd: 0.4, high_usd: 1.05, share: 0.25 },
    standard: { low_usd: 0.72, high_usd: 1.89, share: 0.45 },
    fast: { low_usd: 0.4, high_usd: 1.05, share: 0.25 },
    verifier: { low_usd: 0.08, high_usd: 0.21, share: 0.05 },
  },
};

function api(s: Settings = settings({ spending_limit_usd: 7.5 }), est = EST) {
  return mockApi({
    "GET /api/settings": s,
    "POST /api/estimate": est,
    "POST /api/investigations": new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 }),
    "POST /api/investigations/*/commands": () => new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 }),
  });
}

function show() {
  return render(
    <MemoryRouter initialEntries={["/new"]}>
      <Routes>
        <Route path="/new" element={<NewInvestigation />} />
        <Route path="/" element={<p>home</p>} />
        <Route path="/investigations/:id" element={<p>opened</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const prompt = () => screen.getByRole("textbox", { name: "Your question or claim" });

describe("NewInvestigation", () => {
  it("defaults come from settings", async () => {
    api();
    show();
    expect(await screen.findByDisplayValue("$7.50")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Medium" })).toHaveClass("is-on");
    expect(screen.getByRole("button", { name: "Balanced" })).toHaveClass("is-on");
    expect(screen.getByLabelText("Strong model")).toHaveValue("anthropic/claude-opus-5.5");
    expect(screen.getByLabelText("Verifier model")).toHaveValue("openai/gpt-5.2");
  });

  it('effort line for Medium', async () => {
    api();
    show();
    expect(await screen.findByText("depth 4 · 40 nodes · 8 sources/node · 4 in parallel · 2 independent sources to confirm")).toHaveClass("ng-mono");
    fireEvent.click(screen.getByRole("button", { name: "Low" }));
    expect(screen.getByText("depth 2 · 12 nodes · 4 sources/node · 2 in parallel · 1 independent source to confirm")).toBeInTheDocument();
  });

  it('estimate shows a range and the words "An estimate, not a quote"', async () => {
    const f = api();
    show();
    expect(await screen.findByText("$1.60 – $4.20")).toHaveClass("ng-display");
    expect(screen.getByText(/An estimate, not a quote/)).toBeInTheDocument();
    expect(screen.getByText("$0.72 – $1.89")).toBeInTheDocument();
    expect(screen.getByText("≈ 45%")).toBeInTheDocument();
    const body = JSON.parse(callsTo(f, "POST", "/api/estimate")[0][1]!.body as string);
    expect(body).toMatchObject({ effort: "Medium", tiers: { strong: "anthropic/claude-opus-5.5" } });
  });

  it("unpriced model warns with a link to Settings → Models", async () => {
    api(settings(), { ...EST, unpriced_models: ["openai/gpt-5.2"] });
    show();
    const warn = await screen.findByText(/No price on record\. The spending limit will be approximate/);
    expect(warn).toHaveClass("ng-warn");
    expect(screen.getByRole("link", { name: "Settings → Models" })).toHaveAttribute("href", "/settings#models");
  });

  it("Draft the plan is disabled without a model key, with the hint", async () => {
    api(settings({ keys: { model: { set: false, status: "none", checked_at: null, message: null }, search: { set: false, status: "none", checked_at: null, message: null } } }));
    show();
    fireEvent.change(await screen.findByRole("textbox", { name: "Your question or claim" }), { target: { value: "Is it?" } });
    expect(screen.getByRole("button", { name: "Draft the plan" })).toBeDisabled();
    expect(screen.getByText("Add a model key in Settings → Keys")).toBeInTheDocument();
  });

  it("Draft the plan creates the investigation, sends draft_plan, and opens it", async () => {
    const f = api();
    show();
    fireEvent.change(await screen.findByRole("textbox", { name: "Your question or claim" }), { target: { value: "Is it?" } });
    fireEvent.click(screen.getByRole("button", { name: "Draft the plan" }));
    expect(await screen.findByText("opened")).toBeInTheDocument();
    const body = JSON.parse(callsTo(f, "POST", "/api/investigations")[0][1]!.body as string);
    expect(body.prompt).toBe("Is it?");
    expect(body.settings).toEqual({
      effort: "Medium", preset: "balanced",
      tiers: { strong: "anthropic/claude-opus-5.5", standard: "anthropic/claude-sonnet-5.5", fast: "anthropic/claude-haiku-5.5", verifier: "openai/gpt-5.2" },
      excluded_domains: [], prefer: "none", page_reuse: "1d", spending_limit_usd: 7.5,
    });
    const commands = callsTo(f, "POST", `/api/investigations/${body.id}/commands`);
    expect(commands).toHaveLength(1);
    expect(JSON.parse(commands[0][1]!.body as string)).toMatchObject({ type: "draft_plan", payload: {} });
  });

  it("a refused draft_plan stays on the form and says why", async () => {
    mockApi({
      "GET /api/settings": settings(),
      "POST /api/estimate": EST,
      "POST /api/investigations": new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 }),
      "POST /api/investigations/*/commands": () => new Response(JSON.stringify({ code: "parallel_limit", message: "5 investigations are already active" }), { status: 409 }),
    });
    show();
    fireEvent.change(await screen.findByRole("textbox", { name: "Your question or claim" }), { target: { value: "Is it?" } });
    fireEvent.click(screen.getByRole("button", { name: "Draft the plan" }));
    expect(await screen.findByText(/5 investigations are already active/)).toBeInTheDocument();
    expect(screen.queryByText("opened")).toBeNull();
    expect(screen.getByRole("button", { name: "Draft the plan" })).toBeEnabled();
  });

  it("a saved draft drafts its plan without creating it again", async () => {
    const f = api();
    const draft = { ...row({ id: "inv-9", state: "Draft", prompt: "Saved?" }), settings: { effort: "Medium", preset: "balanced" } as never, root_goal: null };
    render(
      <MemoryRouter initialEntries={["/investigations/inv-9"]}>
        <Routes>
          <Route path="/investigations/:id" element={<NewInvestigation draft={draft} />} />
          <Route path="/" element={<p>home</p>} />
        </Routes>
      </MemoryRouter>,
    );
    const button = await screen.findByRole("button", { name: "Draft the plan" });
    expect(button).toBeEnabled();
    fireEvent.click(button);
    await waitFor(() => expect(callsTo(f, "POST", "/api/investigations/inv-9/commands")).toHaveLength(1));
    expect(callsTo(f, "POST", "/api/investigations")).toHaveLength(0);
  });

  it("double click on Save as draft creates one investigation", async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    const f = mockApi({
      "GET /api/settings": settings(),
      "POST /api/estimate": EST,
      "POST /api/investigations": async () => { await gate; return new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 }); },
    });
    show();
    fireEvent.change(await screen.findByRole("textbox", { name: "Your question or claim" }), { target: { value: "Twice?" } });
    const save = screen.getByRole("button", { name: "Save as draft" });
    fireEvent.click(save);
    fireEvent.click(save);
    release();
    expect(await screen.findByText("home")).toBeInTheDocument();
    const posts = callsTo(f, "POST", "/api/investigations");
    expect(new Set(posts.map(([, i]) => JSON.parse(i!.body as string).id)).size).toBe(1);
    expect(posts).toHaveLength(1);
  });

  it("verifier family warning", async () => {
    api();
    show();
    await screen.findByLabelText("Verifier model");
    expect(screen.queryByText(/same model family as Strong/i)).toBeNull();
    fireEvent.change(screen.getByLabelText("Verifier model"), { target: { value: "anthropic/claude-haiku-5.5" } });
    expect(screen.getByText(/same model family as Strong/i)).toHaveClass("ng-warn");
  });

  it("an invalid spending limit is marked and blocks creating", async () => {
    api();
    show();
    await screen.findByDisplayValue("$7.50");
    fireEvent.change(prompt(), { target: { value: "x" } });
    const limit = await screen.findByDisplayValue("$7.50");
    fireEvent.change(limit, { target: { value: "lots" } });
    fireEvent.blur(limit);
    expect(limit).toHaveClass("is-error");
    expect(screen.getByRole("button", { name: "Save as draft" })).toBeDisabled();
  });
});
