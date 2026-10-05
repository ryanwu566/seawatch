import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nContext";
import { DEFAULT_LAYER_STATE } from "../lib/layerState";
import { LayerControl } from "./LayerControl";

describe("LayerControl historical traffic", () => {
  beforeEach(() => window.localStorage.setItem("seawatch.lang", "en"));

  it("shows a default-off Historical Traffic Density toggle when data is available", () => {
    const onChange = vi.fn();
    render(
      <I18nProvider>
        <LayerControl
          layers={DEFAULT_LAYER_STATE}
          onChange={onChange}
          historicalTrafficAvailable
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open layer menu" }));
    const toggle = screen.getByRole("checkbox", {
      name: "Historical Traffic Density",
    });
    expect(toggle).not.toBeChecked();
    expect(toggle).toBeEnabled();

    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith({
      ...DEFAULT_LAYER_STATE,
      historicalTraffic: true,
    });
  });

  it("keeps the optional toggle disabled when historical traffic is unavailable", () => {
    render(
      <I18nProvider>
        <LayerControl
          layers={DEFAULT_LAYER_STATE}
          onChange={() => undefined}
          historicalTrafficAvailable={false}
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Open layer menu" }));
    expect(screen.getByRole("checkbox", {
      name: /Historical Traffic Density.*Historical traffic unavailable/,
    })).toBeDisabled();
  });
});
