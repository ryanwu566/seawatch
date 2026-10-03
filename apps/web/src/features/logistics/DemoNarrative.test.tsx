import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DemoNarrative } from "./DemoNarrative";

describe("DemoNarrative", () => {
  it("labels the three-stage sequence as illustrative and avoids live-transition claims", () => {
    render(<DemoNarrative />);

    const rail = screen.getByLabelText("Illustrative workflow / 演示流程");
    expect(within(rail).getByText("SENSE")).toBeInTheDocument();
    expect(within(rail).getByText("SURVIVE")).toBeInTheDocument();
    expect(within(rail).getByText("RESPOND")).toBeInTheDocument();
    expect(rail.textContent).toContain("Illustrative workflow / 演示流程");
    expect(rail.textContent).toContain("not an actual network failure");
    expect(rail.textContent).toContain("not an automatic failover");
    expect(rail.textContent).toContain("not a real-time transition");
  });
});
