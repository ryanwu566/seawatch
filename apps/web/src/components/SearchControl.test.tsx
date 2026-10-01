import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { I18nProvider } from "../i18n/I18nContext";
import { SearchControl } from "./SearchControl";
import { DICTIONARIES } from "../i18n/dictionaries";
import type { LiveVesselFeature } from "../api/live";

const zh = DICTIONARIES["zh-Hant"];

function wrap(ui: React.ReactElement) {
  return render(<I18nProvider>{ui}</I18nProvider>);
}

function vessel(id: string, name: string, destination: string | null): LiveVesselFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [120.5, 23.0] },
    properties: {
      provider_id: id,
      sog_knots: 10,
      cog_deg: 90,
      heading_deg: 90,
      nav_status: 0,
      vessel_type: 70,
      name,
      destination,
      observed_at: "2026-10-01T00:00:00Z",
      source: "open_waters",
      synthesized: false,
      data_age_seconds: 5,
    },
  };
}

const vessels = [vessel("v1", "EVER GIVEN", "KHH"), vessel("v2", "OCEAN STAR", "KEL")];

function presetTexts(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll(".preset-btn")).map((b) => b.textContent ?? "");
}

describe("SearchControl", () => {
  it("renders the four quick-location presets", () => {
    const { container } = wrap(
      <SearchControl vessels={vessels} onSelectVessel={() => {}} onFitBounds={() => {}} />,
    );
    const texts = presetTexts(container);
    expect(texts).toContain(zh.presetTaiwanWaters);
    expect(texts).toContain(zh.presetKeelung);
    expect(texts).toContain(zh.presetTaiwanStrait);
    expect(texts).toContain(zh.presetKaohsiung);
  });

  it("searches loaded vessels by name and selects the result", () => {
    const onSelectVessel = vi.fn();
    const { container } = wrap(
      <SearchControl vessels={vessels} onSelectVessel={onSelectVessel} onFitBounds={() => {}} />,
    );
    const input = container.querySelector(".search-input") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "ever" } });
    fireEvent.click(screen.getByText("EVER GIVEN"));
    expect(onSelectVessel).toHaveBeenCalledWith(expect.objectContaining({ id: "v1" }));
  });

  it("searches commercial ports and fits bounds (4-tuple, not inland center)", () => {
    const onFitBounds = vi.fn();
    const { container } = wrap(
      <SearchControl vessels={vessels} onSelectVessel={() => {}} onFitBounds={onFitBounds} />,
    );
    const input = container.querySelector(".search-input") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "kaohsiung" } });
    const portResult = container.querySelector(".result-port");
    expect(portResult).toBeTruthy();
    fireEvent.click((portResult as HTMLElement).closest("button") as HTMLButtonElement);
    expect(onFitBounds).toHaveBeenCalled();
    expect(onFitBounds.mock.calls[0][0]).toHaveLength(4);
  });

  it("fits bounds when a preset is clicked", () => {
    const onFitBounds = vi.fn();
    const { container } = wrap(
      <SearchControl vessels={vessels} onSelectVessel={() => {}} onFitBounds={onFitBounds} />,
    );
    const presets = Array.from(container.querySelectorAll(".preset-btn")) as HTMLButtonElement[];
    const keelung = presets.find((b) => b.textContent === zh.presetKeelung)!;
    fireEvent.click(keelung);
    expect(onFitBounds).toHaveBeenCalledTimes(1);
    expect(onFitBounds.mock.calls[0][0]).toHaveLength(4);
  });

  it("shows a no-results message when nothing matches", () => {
    const { container } = wrap(
      <SearchControl vessels={vessels} onSelectVessel={() => {}} onFitBounds={() => {}} />,
    );
    const input = container.querySelector(".search-input") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "zzzzz-no-match" } });
    expect(container.querySelector(".search-empty")?.textContent).toBe(zh.searchNoResults);
  });
});
