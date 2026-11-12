import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { InstructionComposer } from "./InstructionComposer";
import { Instruction, seqLabel } from "./Instruction";
import type { Instruction as InstructionData } from "../api/types";

beforeEach(() => sessionStorage.clear());
afterEach(() => vi.restoreAllMocks());

const ROOT = { id: "n-root", display_id: "R", label: "the whole investigation" };

function composer(over: Partial<Parameters<typeof InstructionComposer>[0]> = {}) {
  const onSend = vi.fn(() => true);
  render(
    <InstructionComposer target={ROOT} reach={7} hasChildren plan buttonLabel="Re-plan" onSend={onSend} draftKey="inv-1" {...over} />,
  );
  return { onSend, box: screen.getByRole("textbox", { name: "Instruction for R" }) };
}

const foot = () => document.querySelector(".ng-composer__foot")!;

describe("InstructionComposer", () => {
  it("head names the target and its reach", () => {
    composer();
    expect(document.querySelector(".ng-composer__head")).toHaveTextContent("✎︎ Instruct R · the whole investigation · reaches 7 nodes");
    expect(document.querySelector(".ng-composer")).not.toHaveClass("is-locked");
  });

  it("foot copy from the README: plan, coordinator, leaf", () => {
    composer();
    expect(foot()).toHaveTextContent("The plan is redrawn each time. You can change what is investigated, not what is concluded.");
  });

  it("coordinator and leaf foot copy on the board", () => {
    const { unmount } = render(<InstructionComposer target={{ id: "d2", display_id: "D2", label: "What astronauts report" }} reach={4} hasChildren buttonLabel="Send instruction" onSend={() => true} />);
    expect(foot()).toHaveTextContent("Takes effect at each node's next step. D2 will re-plan its children.");
    unmount();
    render(<InstructionComposer target={{ id: "p1", display_id: "P1", label: "Visible from orbit" }} reach={1} hasChildren={false} buttonLabel="Send instruction" onSend={() => true} />);
    expect(foot()).toHaveTextContent("Takes effect at the node's next step.");
    expect(document.querySelector(".ng-composer__head")).toHaveTextContent("reaches 1 node");
  });

  it("composer foot turns warn for conclusion-like text and still sends", () => {
    const { onSend, box } = composer();
    fireEvent.change(box, { target: { value: "The wall is obviously visible, just confirm it." } });
    const warn = foot().querySelector(".ng-warn");
    expect(warn).toHaveTextContent("You can change what is investigated, not what is concluded. Netgrip will check this as a hypothesis.");
    const button = screen.getByRole("button", { name: /Re-plan/ });
    expect(button).not.toHaveClass("ng-btn--steer");
    fireEvent.click(button);
    expect(onSend).toHaveBeenCalledWith("The wall is obviously visible, just confirm it.");
  });

  it("⌘↵ sends; an empty draft does not", () => {
    const { onSend, box } = composer();
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Re-plan" })).toBeDisabled();
    fireEvent.change(box, { target: { value: "Only human eyes." } });
    fireEvent.keyDown(box, { key: "Enter", metaKey: true });
    expect(onSend).toHaveBeenCalledWith("Only human eyes.");
  });

  it("the draft is kept per node in sessionStorage and cleared after sending", async () => {
    const first = render(<InstructionComposer target={ROOT} reach={7} hasChildren plan buttonLabel="Re-plan" onSend={() => true} draftKey="inv-1" />);
    fireEvent.change(screen.getByRole("textbox", { name: "Instruction for R" }), { target: { value: "Leave out tourism." } });
    first.unmount();
    const other = render(<InstructionComposer target={{ id: "d2", display_id: "D2", label: "x" }} reach={1} hasChildren={false} buttonLabel="Send" onSend={() => true} draftKey="inv-1" />);
    expect(screen.getByRole("textbox", { name: "Instruction for D2" })).toHaveValue("");
    other.unmount();
    const again = render(<InstructionComposer target={ROOT} reach={7} hasChildren plan buttonLabel="Re-plan" onSend={() => true} draftKey="inv-1" />);
    const box = screen.getByRole("textbox", { name: "Instruction for R" });
    expect(box).toHaveValue("Leave out tourism.");
    fireEvent.click(screen.getByRole("button", { name: "Re-plan" }));
    await waitFor(() => expect(box).toHaveValue(""));
    again.unmount();
    render(<InstructionComposer target={ROOT} reach={7} hasChildren plan buttonLabel="Re-plan" onSend={() => true} draftKey="inv-1" />);
    expect(screen.getByRole("textbox", { name: "Instruction for R" })).toHaveValue("");
  });

  it("a send that fails keeps the draft", async () => {
    const onSend = vi.fn(async () => false);
    render(<InstructionComposer target={ROOT} reach={7} hasChildren plan buttonLabel="Re-plan" onSend={onSend} draftKey="inv-1" />);
    const box = screen.getByRole("textbox", { name: "Instruction for R" });
    fireEvent.change(box, { target: { value: "Keep me." } });
    fireEvent.click(screen.getByRole("button", { name: "Re-plan" }));
    await waitFor(() => expect(onSend).toHaveBeenCalled());
    expect(box).toHaveValue("Keep me.");
  });

  it("sent shows the is-sent wording and disables the button", () => {
    composer({ sent: true, sentLabel: "Re-planning…" });
    const button = screen.getByRole("button", { name: "Re-planning…" });
    expect(button).toHaveClass("is-sent");
    expect(button).toBeDisabled();
  });

  it("locked explains what to do instead and takes no text", () => {
    render(<InstructionComposer target={ROOT} reach={7} hasChildren locked buttonLabel="Send instruction" onSend={() => true} />);
    expect(document.querySelector(".ng-composer")).toHaveClass("is-locked");
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(foot()).toHaveTextContent("The root goal cannot be re-planned once research is running. Instruct a branch, or stop and start a new investigation.");
  });
});

const ids = { a: "P1", b: "D2", c: "D5", d: "D1" };
const questions = { c: "Use of the claim in tourism marketing", d: "Where does the claim come from?" };
function instruction(over: Partial<InstructionData> = {}): InstructionData {
  return {
    id: "i1", node_id: "root", text: "Leave out tourism marketing. Include where the claim came from.",
    state: "applied", queued_seq: 14, applied_seq: 19, undone: false,
    diff: { kept: ["a", "b"], superseded: ["c"], proposed: ["d"], notes: ["P1 kept: premises are always checked"] },
    ...over,
  };
}

describe("Instruction", () => {
  it("applied: the text verbatim on steer-wash, stamped with its sequence number, with its ng-diff", () => {
    render(<Instruction instruction={instruction()} nodeDisplayIds={ids} nodeQuestions={questions} variant="applied" versionLabel="plan v1 → v2" />);
    const block = document.querySelector(".ng-instr")!;
    expect(block).not.toHaveClass("ng-instr--queued");
    expect(block.querySelector(".ng-instr__text")).toHaveTextContent("Leave out tourism marketing. Include where the claim came from.");
    expect(seqLabel(14)).toMatch(/^#\d{4}$/);
    expect(block.querySelector(".ng-instr__meta")).toHaveTextContent(`You · ${seqLabel(14)}`);
    expect(block.querySelector(".ng-instr__meta")).toHaveTextContent(`plan v1 → v2 · applied ${seqLabel(19)}`);
    expect(block.querySelector(".ng-diff__k")).toHaveTextContent("= kept P1, D2");
    expect(block.querySelector(".ng-diff__s")).toHaveTextContent("↺ superseded D5 Use of the claim in tourism marketing");
    expect(block.querySelector(".ng-diff__n")).toHaveTextContent("+ proposed D1 Where does the claim come from?");
  });

  it('diff note "P1 kept: premises are always checked" is rendered', () => {
    render(<Instruction instruction={instruction()} nodeDisplayIds={ids} variant="applied" />);
    expect(screen.getByText("P1 kept: premises are always checked").closest(".ng-diff")).not.toBeNull();
  });

  it("a failed re-plan shows only its note", () => {
    render(<Instruction instruction={instruction({ diff: { kept: [], superseded: [], proposed: [], notes: ["Re-plan failed: the model did not answer."] } })} nodeDisplayIds={ids} variant="applied" />);
    const diff = document.querySelector(".ng-diff")!;
    expect(diff).toHaveTextContent("Re-plan failed: the model did not answer.");
    expect(diff.querySelector(".ng-diff__k, .ng-diff__s, .ng-diff__n")).toBeNull();
  });

  it("queued is dashed and says what it waits for; inherited names its origin", () => {
    const { unmount } = render(<Instruction instruction={instruction({ state: "queued", applied_seq: null, diff: null })} nodeDisplayIds={ids} variant="queued" />);
    expect(document.querySelector(".ng-instr")).toHaveClass("ng-instr--queued");
    expect(document.querySelector(".ng-instr__meta")).toHaveTextContent("queued · applies when the re-plan is drawn");
    expect(document.querySelector(".ng-diff")).toBeNull();
    unmount();
    render(<Instruction instruction={instruction()} nodeDisplayIds={ids} variant="inherited" from="D2" />);
    expect(document.querySelector(".ng-instr")).toHaveClass("ng-instr--inherited");
    expect(document.querySelector(".ng-instr__meta")).toHaveTextContent("Inherited from D2");
  });

  it("an undone instruction says so", () => {
    render(<Instruction instruction={instruction({ state: "undone", undone: true })} nodeDisplayIds={ids} variant="applied" />);
    expect(document.querySelector(".ng-instr__meta")).toHaveTextContent("undone");
  });
});
