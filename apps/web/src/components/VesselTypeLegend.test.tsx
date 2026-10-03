import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VesselTypeLegend } from "./VesselTypeLegend";

describe("VesselTypeLegend", () => {
  it("shows a compact type-only maritime legend without threat semantics", () => {
    render(<VesselTypeLegend />);

    expect(screen.getByRole("region", { name: "Vessel type legend" })).toBeInTheDocument();
    for (const label of [
      "Cargo",
      "Tanker",
      "Fishing",
      "Passenger",
      "Tug / Service",
      "Research / Survey",
      "Government / Law Enforcement",
      "Pleasure / Sailing",
      "Other / Unknown",
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(document.body.textContent).not.toMatch(/threat|risk|hostile|illegal/i);
  });
});
