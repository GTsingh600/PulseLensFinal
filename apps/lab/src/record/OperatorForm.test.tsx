import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { OperatorForm } from "./OperatorForm";

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("OperatorForm", () => {
  it("submits a genuine-session label", () => {
    const onSubmit = vi.fn();
    render(<OperatorForm onSubmit={onSubmit} />);
    fill("Person code", "p03");
    fill("Device code", "D01");
    fill("Consent reference", "C-11");
    fireEvent.click(screen.getByLabelText("Genuine"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onSubmit).toHaveBeenCalledWith({
      person: "P03", device: "D01", light: "normal", kind: "genuine", tool: null, consent_ref: "C-11",
    });
  });

  it("refuses to continue without the required fields, and says why", () => {
    const onSubmit = vi.fn();
    render(<OperatorForm onSubmit={onSubmit} />);
    fill("Person code", "Ravi");
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/pseudonymous code like P01/)).toBeTruthy();
    expect(screen.getByText(/Pick genuine or attack/)).toBeTruthy();
  });

  it("requires an attack tool for attack sessions", () => {
    const onSubmit = vi.fn();
    render(<OperatorForm onSubmit={onSubmit} />);
    fill("Person code", "P02");
    fill("Device code", "D05");
    fill("Consent reference", "C-12");
    fireEvent.click(screen.getByLabelText("Attack"));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Attack tool"), { target: { value: "liveswap" } });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ kind: "attack", tool: "liveswap" }));
  });
});
