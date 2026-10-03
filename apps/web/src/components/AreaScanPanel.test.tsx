import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n/I18nContext";
import { DICTIONARIES } from "../i18n/dictionaries";
import type { AreaScanResponse } from "../api/live";
import { AreaScanPanel } from "./AreaScanPanel";

const t = DICTIONARIES["zh-Hant"];
const geometry: GeoJSON.Polygon = {
  type: "Polygon",
  coordinates: [[[120, 22], [121, 22], [121, 23], [120, 22]]],
};

const result: AreaScanResponse = {
  source: "datalastic",
  scanned_at: "2026-10-03T02:00:00Z",
  cached: true,
  scan: { geometry_type: "Polygon", provider_queries: 3 },
  total: 37,
  vessels: [],
};

function renderPanel(
  props: Partial<React.ComponentProps<typeof AreaScanPanel>> = {},
) {
  const defaults: React.ComponentProps<typeof AreaScanPanel> = {
    drawMode: null,
    geometry: null,
    loading: false,
    result: null,
    error: null,
    authenticated: true,
    authenticating: false,
    onDrawMode: vi.fn(),
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
    renderPanel({ geometry, onScan });

    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    expect(onScan).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: t.scanArea }));
    expect(onScan).toHaveBeenCalledTimes(1);
  });

  it("keeps rescan and clear available while loading and shows the result summary", () => {
    const { rerender } = renderPanel({ geometry, loading: true });
    fireEvent.click(screen.getByRole("button", { name: t.areaScan }));
    expect(screen.getByRole("button", { name: t.areaScanning })).toBeEnabled();
    expect(screen.getByRole("button", { name: t.clearAreaScan })).toBeEnabled();

    rerender(
      <I18nProvider>
        <AreaScanPanel
          drawMode={null}
          geometry={geometry}
          loading={false}
          result={result}
          error={null}
          authenticated
          authenticating={false}
          onDrawMode={() => {}}
          onAuthenticate={() => {}}
          onScan={() => {}}
          onClear={() => {}}
        />
      </I18nProvider>,
    );
    expect(screen.getByText("37")).toBeInTheDocument();
    expect(screen.getByText("Datalastic Live AIS")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(t.areaScanCached)).toBeInTheDocument();
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
    renderPanel({ geometry, authenticated: false, onAuthenticate });
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
});
