import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./pages/Dashboard", () => ({ Dashboard: () => <div>research</div> }));
vi.mock("./pages/LiveDashboard", () => ({ LiveDashboard: () => <div>live-view</div> }));
vi.mock("./features/logistics/LogisticsPanel", () => ({ LogisticsPanel: () => null }));
vi.mock("./features/logistics/LogisticsView", () => ({
  LogisticsView: (props: { demoMode?: boolean; initialScenarioId?: string }) => (
    <div
      data-testid="logistics-view"
      data-demo={String(Boolean(props.demoMode))}
      data-scenario={props.initialScenarioId ?? ""}
    />
  ),
}));

import App, { isResilienceDemo } from "./App";

afterEach(() => window.history.replaceState({}, "", "/"));

describe("resilience demo entry", () => {
  it("recognizes only the approved demo query", () => {
    expect(isResilienceDemo("?demo=resilience")).toBe(true);
    expect(isResilienceDemo("?demo=other")).toBe(false);
  });

  it("opens logistics with the fixed Kaohsiung scenario", () => {
    window.history.replaceState({}, "", "/?demo=resilience");
    render(<App />);

    const view = screen.getByTestId("logistics-view");
    expect(view).toHaveAttribute("data-demo", "true");
    expect(view).toHaveAttribute("data-scenario", "kaohsiung-disruption");
  });
});
