import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { AppHeader } from "./AppHeader";
import { DICTIONARIES } from "../i18n/dictionaries";
import type { ModePresentation } from "../lib/resilience";

function wrap(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

describe("AppHeader status pill", () => {
  it("renders the explicit backend mode presentation", () => {
    const presentation: ModePresentation = {
      mode: "EDGE_LIVE",
      label: DICTIONARIES["zh-Hant"].modeEdge,
      coverageLabel: DICTIONARIES["zh-Hant"].coverageEdge,
      detail: DICTIONARIES["zh-Hant"].edgeCoverageNote,
      powerLabel: DICTIONARIES["zh-Hant"].batteryUps,
      powerNote: DICTIONARIES["zh-Hant"].powerRequirement,
    };
    const { container } = wrap(<AppHeader presentation={presentation} />);
    expect(screen.getByText("本地 AIS 接收")).toBeInTheDocument();
    expect(container.querySelector(".live-pill.live-edge_live")).toBeTruthy();
  });
});
