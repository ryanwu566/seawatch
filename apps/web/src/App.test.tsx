import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./pages/Dashboard", () => ({ Dashboard: () => <div>research</div> }));
vi.mock("./pages/LiveDashboard", () => ({
  LiveDashboard: (props: { vesselDemo?: boolean }) => (
    <div data-testid="live-view" data-vessel-demo={String(Boolean(props.vesselDemo))} />
  ),
}));
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

import App, { isResilienceDemo, isVesselDemo } from "./App";
import { DICTIONARIES } from "./i18n/dictionaries";

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

describe("vessel demo entry", () => {
  it("recognizes only the explicit vessel demo query", () => {
    expect(isVesselDemo("?demo=vessel")).toBe(true);
    expect(isVesselDemo("")).toBe(false);
    expect(isVesselDemo("?demo=resilience")).toBe(false);
    expect(isVesselDemo("?demo=other")).toBe(false);
  });

  it("opts the live dashboard into the illustrative vessel scenario", () => {
    window.history.replaceState({}, "", "/?demo=vessel");
    render(<App />);

    expect(screen.getByTestId("live-view")).toHaveAttribute(
      "data-vessel-demo",
      "true",
    );
  });

  it("does not silently enter the vessel scenario without the query", () => {
    render(<App />);

    expect(screen.getByTestId("live-view")).toHaveAttribute(
      "data-vessel-demo",
      "false",
    );
  });
});

describe("primary navigation", () => {
  it("renders English navigation labels by default", () => {
    window.localStorage.clear();
    render(<App />);

    expect(screen.getByRole("button", { name: DICTIONARIES.en.logistics.navLiveMap }))
      .toBeInTheDocument();
    expect(screen.getByRole("button", { name: DICTIONARIES.en.logistics.navLogistics }))
      .toBeInTheDocument();
    expect(document.querySelector(".app-nav")?.textContent).not.toMatch(/[\u3400-\u9fff]/u);
  });
});
