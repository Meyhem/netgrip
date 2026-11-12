import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Settings } from "./Settings";
import { NewInvestigation } from "./NewInvestigation";
import { callsTo, mockApi } from "../test/fetch";
import { POOLS, settings } from "../test/fixtures";

afterEach(() => vi.unstubAllGlobals());

const STORAGE = { total_bytes: 0, investigations: 0, pages: 0, data_dir: "/d" };

describe("review fixes", () => {
  it("Settings retries until the service answers", async () => {
    let up = false;
    mockApi({
      "GET /api/settings": () => (up ? settings() : new Response("{}", { status: 503 })),
      "GET /api/system/pools": POOLS, "GET /api/system/storage": STORAGE,
    });
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Retrying every 3 seconds");
    up = true;
    expect(await screen.findByLabelText("Medium max nodes", undefined, { timeout: 5000 })).toBeInTheDocument();
  }, 8000);

  it("New investigation retries until the service answers", async () => {
    let up = false;
    mockApi({
      "GET /api/settings": () => (up ? settings() : new Response("{}", { status: 503 })),
      "POST /api/estimate": new Response("{}", { status: 503 }),
    });
    render(<MemoryRouter><NewInvestigation /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Retrying every 3 seconds");
    up = true;
    expect(await screen.findByLabelText("Strong model", undefined, { timeout: 5000 })).toBeInTheDocument();
  }, 8000);

  it("a failed key save says so, and a key is sent trimmed", async () => {
    const f = mockApi({
      "GET /api/settings": settings(), "GET /api/system/pools": POOLS, "GET /api/system/storage": STORAGE,
      "PUT /api/settings/keys/model": new Response(JSON.stringify({ detail: "boom" }), { status: 500 }),
    });
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const keys = (await screen.findByText("Model provider")).closest("section")!;
    fireEvent.click(within(keys).getAllByRole("button", { name: "Replace" })[0]);
    fireEvent.change(within(keys).getByLabelText("Model provider key"), { target: { value: "  sk-abc\n" } });
    fireEvent.click(within(keys).getByRole("button", { name: "Save key" }));
    expect(await within(keys).findByText(/Not saved/)).toHaveClass("is-error");
    expect(document.body.textContent).not.toContain("sk-abc"); // only the user's own input holds it, for a retry
    expect(JSON.parse(callsTo(f, "PUT", "/api/settings/keys/model")[0][1]!.body as string)).toEqual({ value: "sk-abc" });
  });

  it("a refused PATCH puts the server's value back in the field", async () => {
    mockApi({
      "GET /api/settings": settings(), "GET /api/system/pools": POOLS, "GET /api/system/storage": STORAGE,
      "PATCH /api/settings": new Response(JSON.stringify({ detail: [] }), { status: 422 }),
    });
    render(<MemoryRouter><Settings /></MemoryRouter>);
    const input = await screen.findByLabelText("Default limit");
    fireEvent.change(input, { target: { value: "$9.00" } });
    fireEvent.blur(input);
    await screen.findByText(/Not saved/);
    await waitFor(() => expect(screen.getByLabelText("Default limit")).toHaveValue("$5.00"));
  });
});
