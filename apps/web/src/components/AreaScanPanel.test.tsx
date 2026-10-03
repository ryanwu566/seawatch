import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nContext";
import { DICTIONARIES } from "../i18n/dictionaries";
import type { AreaScanPlan, AreaScanResponse } from "../api/live";
import { AreaScanPanel } from "./AreaScanPanel";

const t = DICTIONARIES.en;
const geometry: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
};

const result: AreaScanResponse = {
  source: "datalastic",
  scanned_at: "2026-10-03T02:00:00Z",
  cached: true,
  scan: { geometry_type: "Polygon", provider_queries: 3 },
  total: 1,
  vessels: [
    {
      type: "Feature",
      id: "cargo-1",
      geometry: { type: "Point", coordinates: [120.5, 22.5] },
      properties: {
        provider_id: "cargo-1",
        sog_knots: 8,
        cog_deg: 90,
        heading_deg: 90,
        nav_status: null,
        vessel_type: null,
        provider_vessel_type: "Cargo",
        provider_vessel_type_specific: "Container Ship",
        name: "ONE",
        destination: null,
        observed_at: "2026-10-03T01:59:00Z",
        source: "datalastic",
        synthesized: false,
        data_age_seconds: 60,
      },
    },
  ],
};

const plan: AreaScanPlan = {
  area_square_km: 123.45,
  provider_queries: 3,
  max_provider_queries: 16,
  can_scan: true,
  reason: null,
};

function renderPanel(
  props: Partial<React.ComponentProps<typeof AreaScanPanel>> = {},
) {
  const defaults: React.ComponentProps<typeof AreaScanPanel> = {
    drawMode: null,
    geometry: null,
    loading: false,
    planning: false,
    plan: null,
    result: null,
    error: null,
    authenticated: true,
    authenticating: false,
    providerAvailable: true,
    operatorAuthenticationRequired: false,
    onDrawMode: vi.fn(),
    onOpen: vi.fn(),
    onAuthenticate: vi.fn(),
    onScan: vi.fn(),
    onClear: vi.fn(),
  };
  return render(
    <I18nProvider>
      <AreaScanPanel {...defaults} {...props} />
    </I18nProvider>,
  );
}

describe("AreaScanPanel", () => {
  it("enters polygon or rectangle draw mode without scanning", () => {
    const onDrawMode = vi.fn();
    const onScan = vi.fn();
    renderPanel({ onDrawMode, onScan });

    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    fireEvent.click(screen.getByRole("button", { name: t.areaScanPolygon }));
    fireEvent.click(screen.getByRole("button", { name: t.areaScanRectangle }));

    expect(onDrawMode).toHaveBeenNthCalledWith(1, "polygon");
    expect(onDrawMode).toHaveBeenNthCalledWith(2, "rectangle");
    expect(onScan).not.toHaveBeenCalled();
  });

  it("calls scan only from the explicit Scan Area button", () => {
    const onScan = vi.fn();
    renderPanel({ geometry, plan, onScan });

    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    expect(onScan).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));
    expect(onScan).toHaveBeenCalledTimes(1);
  });

  it("prevents repeat scans while loading and shows the result summary", () => {
    const { rerender } = renderPanel({ geometry, loading: true, plan });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    expect(screen.getByRole("button", { name: t.areaScanning })).toBeDisabled();
    expect(screen.getByRole("button", { name: t.clearAreaScan })).toBeEnabled();

    rerender(
      <I18nProvider>
        <AreaScanPanel
          drawMode={null}
          geometry={geometry}
          loading={false}
          planning={false}
          plan={plan}
          result={result}
          error={null}
          authenticated
          authenticating={false}
          providerAvailable
          operatorAuthenticationRequired={false}
          onDrawMode={() => {}}
          onOpen={() => {}}
          onAuthenticate={() => {}}
          onScan={() => {}}
          onClear={() => {}}
        />
      </I18nProvider>,
    );
    expect(screen.getAllByText("1")).toHaveLength(2);
    expect(screen.getByText("Datalastic Live AIS")).toBeInTheDocument();
    expect(screen.getAllByText("3")).toHaveLength(2);
    expect(screen.getByText(t.areaScanCached)).toBeInTheDocument();
    expect(screen.getByText("Cargo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.areaScanAgain })).toBeEnabled();
    expect(document.body.textContent).not.toMatch(/[\u3400-\u9fff]/u);
  });

  it("shows the selected area and exact non-billable query plan", () => {
    renderPanel({ geometry, plan });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));

    expect(screen.getByText("~ 123.45 km²")).toBeInTheDocument();
    expect(screen.getByText(t.areaScanEstimatedQueries)).toBeInTheDocument();
    expect(screen.getByText(t.areaScanMaximumAllowed)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t.scanArea })).toBeEnabled();
  });

  it("disables scanning and explains an oversized selected area", () => {
    renderPanel({
      geometry,
      plan: { ...plan, provider_queries: null, can_scan: false, reason: "too_large" },
    });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));

    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(t.areaScanTooLargeShort);
  });

  it("keeps Scan Area disabled when the Datalastic provider is unavailable", () => {
    renderPanel({ geometry, plan, providerAvailable: false });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));

    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
  });

  it("shows provider unavailable and clears the active selection", () => {
    const onClear = vi.fn();
    renderPanel({ geometry, error: t.datalasticUnavailable, onClear });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    expect(screen.getByRole("alert")).toHaveTextContent(t.datalasticUnavailable);
    fireEvent.click(screen.getByRole("button", { name: t.clearAreaScan }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("authenticates once, clears the credential field, and requires a session", () => {
    const onAuthenticate = vi.fn();
    renderPanel({
      geometry,
      authenticated: false,
      operatorAuthenticationRequired: true,
      onAuthenticate,
    });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));

    const input = screen.getByLabelText(t.areaScanOperatorCredential);
    expect(input).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: t.scanArea })).toBeDisabled();
    fireEvent.change(input, { target: { value: "temporary-operator-credential" } });
    fireEvent.click(screen.getByRole("button", { name: t.areaScanAuthenticate }));

    expect(onAuthenticate).toHaveBeenCalledWith("temporary-operator-credential");
    expect(input).toHaveValue("");
    expect(document.body.textContent).not.toContain("DATALASTIC_API_KEY");
  });

  it("hides the password while loopback auto-auth is active and exposes draw controls", () => {
    const onOpen = vi.fn();
    renderPanel({ authenticated: true, operatorAuthenticationRequired: false, onOpen });

    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.queryByLabelText(t.areaScanOperatorCredential)).toBeNull();
    expect(screen.getByRole("button", { name: t.areaScanPolygon })).toBeEnabled();
    expect(screen.getByRole("button", { name: t.areaScanRectangle })).toBeEnabled();
  });
});
