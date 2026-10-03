import { useState } from "react";
import type { AreaScanResponse } from "../api/live";
import { useI18n } from "../i18n/I18nContext";

export type AreaDrawMode = "polygon" | "rectangle" | null;

interface AreaScanPanelProps {
  drawMode: AreaDrawMode;
  geometry: GeoJSON.Polygon | null;
  loading: boolean;
  result: AreaScanResponse | null;
  error: string | null;
  authenticated: boolean;
  authenticating: boolean;
  onDrawMode: (mode: Exclude<AreaDrawMode, null>) => void;
  onAuthenticate: (operatorCredential: string) => void;
  onScan: () => void;
  onClear: () => void;
}

export function AreaScanPanel({
  drawMode,
  geometry,
  loading,
  result,
  error,
  authenticated,
  authenticating,
  onDrawMode,
  onAuthenticate,
  onScan,
  onClear,
}: AreaScanPanelProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [operatorCredential, setOperatorCredential] = useState("");

  const authenticate = () => {
    const credential = operatorCredential.trim();
    if (!credential || authenticating) return;
    onAuthenticate(credential);
    setOperatorCredential("");
  };

  if (!open) {
    return (
      <button type="button" className="area-scan-entry" onClick={() => setOpen(true)}>
        {t.areaScan}
      </button>
    );
  }

  return (
    <aside className="area-scan-panel" aria-label={t.areaScan}>
      <div className="area-scan-heading">
        <strong>{t.areaScan}</strong>
        <button type="button" className="area-scan-close" onClick={() => setOpen(false)}>
          ×
        </button>
      </div>

      <div className="area-scan-modes">
        <button
          type="button"
          className={drawMode === "polygon" ? "active" : ""}
          onClick={() => onDrawMode("polygon")}
        >
          {t.areaScanPolygon}
        </button>
        <button
          type="button"
          className={drawMode === "rectangle" ? "active" : ""}
          onClick={() => onDrawMode("rectangle")}
        >
          {t.areaScanRectangle}
        </button>
      </div>

      <p className="area-scan-hint">{geometry ? t.areaScanReady : t.areaScanDrawHint}</p>

      {authenticated ? (
        <p className="area-scan-authenticated" role="status">
          {t.areaScanAuthenticated}
        </p>
      ) : (
        <div className="area-scan-auth">
          <label>
            <span>{t.areaScanOperatorCredential}</span>
            <input
              type="password"
              autoComplete="current-password"
              value={operatorCredential}
              placeholder={t.areaScanOperatorCredentialHint}
              onChange={(event) => setOperatorCredential(event.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={!operatorCredential.trim() || authenticating}
            onClick={authenticate}
          >
            {authenticating ? t.areaScanAuthenticating : t.areaScanAuthenticate}
          </button>
        </div>
      )}

      {result && (
        <dl className="area-scan-summary" aria-live="polite">
          <div><dt>{t.areaScanResults}</dt><dd>{result.total}</dd></div>
          <div><dt>{t.source}</dt><dd>{t.datalasticLiveAis}</dd></div>
          <div><dt>{t.areaScanTime}</dt><dd>{new Date(result.scanned_at).toLocaleTimeString()}</dd></div>
          <div><dt>{t.areaScanQueries}</dt><dd>{result.scan.provider_queries}</dd></div>
        </dl>
      )}
      {result?.cached && <span className="area-scan-cached">{t.areaScanCached}</span>}
      {error && <p className="area-scan-error" role="alert">{error}</p>}

      <div className="area-scan-actions">
        <button
          type="button"
          disabled={!geometry || !authenticated}
          onClick={onScan}
        >
          {loading ? t.areaScanning : t.scanArea}
        </button>
        <button type="button" onClick={onClear}>
          {t.clearAreaScan}
        </button>
      </div>
    </aside>
  );
}
