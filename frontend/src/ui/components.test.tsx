import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BudgetMeter } from "./BudgetMeter";
import { Button } from "./Button";
import { ActivityLine } from "./ActivityLine";
import { NumberField, Seg, KeyField } from "./Field";
import { Banner } from "./Banner";
import { bytes, duration, money, moneyOf } from "../lib/format";

describe("format", () => {
  it("money", () => {
    expect(money(1.8)).toBe("$1.80");
    expect(money(0)).toBe("$0.00");
    expect(moneyOf(1.84, 5)).toBe("$1.84 / $5.00");
  });
  it("duration and bytes", () => {
    expect(duration(4320)).toBe("1h 12m");
    expect(duration(59)).toBe("0m");
    expect(bytes(387 * 1024 * 1024)).toBe("387 MB");
    expect(bytes(100 * 1024)).toBe("0.1 MB");
    expect(bytes(0)).toBe("0 MB");
  });
});

describe("BudgetMeter", () => {
  it("at 85% has ng-meter--warn", () => {
    const { container } = render(<BudgetMeter label="Spend" value={4.25} max={5} format="money" />);
    expect(container.firstChild).toHaveClass("ng-meter", "ng-meter--warn");
    expect(container).toHaveTextContent("$4.25 / $5.00");
  });
  it("at 100% has --danger; approximate shows ≈", () => {
    const { container } = render(<BudgetMeter label="Spend" value={5} max={5} format="money" approximate />);
    expect(container.firstChild).toHaveClass("ng-meter--danger");
    expect(container).toHaveTextContent("≈ $5.00 / $5.00");
  });
  it("count format", () => {
    const { container } = render(<BudgetMeter label="Nodes" value={16} max={40} format="count" />);
    expect(container.firstChild).not.toHaveClass("ng-meter--warn");
    expect(container).toHaveTextContent("16 / 40");
  });
});

describe("Button", () => {
  it("sent shows the sent label, is-sent, disabled", () => {
    render(<Button variant="steer" sent sentLabel="Pausing…">Pause</Button>);
    const b = screen.getByRole("button", { name: "Pausing…" });
    expect(b).toHaveClass("ng-btn", "ng-btn--steer", "is-sent");
    expect(b).toBeDisabled();
  });
});

describe("ActivityLine", () => {
  it("renders verb and detail; retry uses is-retry", () => {
    const { container } = render(<ActivityLine activity="Retrying" detail="esa.int timed out · full browser next" retry={{ n: 2, m: 3 }} />);
    expect(container.querySelector(".ng-activity__verb")).toHaveClass("is-retry");
    expect(container).toHaveTextContent("Retrying 2 of 3esa.int timed out");
  });
  it("Waiting on children is shown as Waiting", () => {
    const { container } = render(<ActivityLine activity="Waiting on children" detail="on 2 children" />);
    expect(container.querySelector(".ng-activity__verb")).toHaveTextContent("Waiting");
  });
});

describe("Fields", () => {
  it("Seg marks the chosen option", () => {
    const onChange = vi.fn();
    render(<Seg options={["Low", "Medium", "High"]} value="Medium" onChange={onChange} />);
    expect(screen.getByRole("button", { name: "Medium" })).toHaveClass("is-on");
    fireEvent.click(screen.getByRole("button", { name: "High" }));
    expect(onChange).toHaveBeenCalledWith("High");
  });
  it("NumberField commits numbers on blur and marks non-numbers is-error", () => {
    const onCommit = vi.fn();
    render(<NumberField aria-label="n" value={4} onCommit={onCommit} />);
    const input = screen.getByLabelText("n");
    fireEvent.change(input, { target: { value: "abc" } });
    fireEvent.blur(input);
    expect(input).toHaveClass("is-error");
    expect(onCommit).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "6" } });
    fireEvent.blur(input);
    expect(onCommit).toHaveBeenCalledWith(6);
    expect(input).not.toHaveClass("is-error");
  });
  it("KeyField shows status, no value; Replace reveals an empty input", () => {
    const onReplace = vi.fn().mockResolvedValue(undefined);
    render(<KeyField label="Model key" status={{ set: true, status: "set", checked_at: null, message: null }} onReplace={onReplace} />);
    expect(screen.getByText("Key set")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Replace" }));
    expect(screen.getByLabelText("Model key")).toHaveValue("");
  });
});

describe("Banner", () => {
  it("has tone class", () => {
    const { container } = render(<Banner tone="warn" title="Netgrip cannot reach its service">Retrying.</Banner>);
    expect(container.firstChild).toHaveClass("ng-banner", "ng-banner--warn");
  });
});
