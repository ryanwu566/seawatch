import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HistoricalTrafficLegend } from "./HistoricalTrafficLegend";

describe("HistoricalTrafficLegend", () => {
  it("describes relative historical presence without threat semantics", () => {
    const { container } = render(<HistoricalTrafficLegend />);

    expect(screen.getByText("Historical Traffic Density")).toBeInTheDocument();
    expect(screen.getByText("Low")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText(/standardized hourly vessel presence/)).toBeInTheDocument();
    expect(screen.getByText(/~0.1° cells/)).toBeInTheDocument();
    expect(screen.getByText(/not raw\/message-level AIS/)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/risk|threat|danger|suspicious/i);
  });
});
