import { useState } from "react";
import type { AreaScanPlan, AreaScanResponse } from "../api/live";
import { useI18n } from "../i18n/I18nContext";
import { countVesselCategories } from "../lib/vesselCategory";

export type AreaDrawMode = "polygon" | "rectangle" | null;

interface AreaScanPanelProps {
  drawMode: AreaDrawMode;
  geometry: GeoJSON.Polygon | null;
  loading: boolean;
  planning: boolean;
  plan: AreaScanPlan | null;
  result: AreaScanResponse | null;
  error: string | null;
  authenticated: boolean;
  authenticating: boolean;
  providerAvailable: boolean;
  providerRefreshAvailable: boolean;
  providerRefreshing: boolean;
  providerRefreshMessage: string | null;
  operatorAuthenticationRequired: boolean;
  onDrawMode: (mode: Exclude<AreaDrawMode, null>) => void;
  onOpen: () => void;
  onAuthenticate: (operatorCredential: string) => void;
  onRefreshProvider: () => void;
  onScan: () => void;
  onClear: () => void;
}

export function AreaScanPanel({
  drawMode,
  geometry,
  loading,
  planning,
  plan,
  result,
  error,
  authenticated,
  authenticating,
  providerAvailable,
  providerRefreshAvailable,
  providerRefreshing,
  providerRefreshMessage,
  operatorAuthenticationRequired,
  onDrawMode,
  onOpen,
  onAuthenticate,
  onRefreshProvider,
  onScan,
  onClear,
}: AreaScanPanelProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [operatorCredential, setOperatorCredential] = useState("");
  const categoryCounts = result ? countVesselCategories(result.vessels) : [];
  const canScan = Boolean(
    geometry &&
    authenticated &&
    providerAvailable &&
    !loading &&
    !planning &&
    plan?.can_scan,
  );

  const authenticate = () => {
    const credential = operatorCredential.trim();
    if (!credential || authenticating) return;
    onAuthenticate(credential);
    setOperatorCredential("");
  };

  if (!open) {
    return (
      <button
        type="button"
        className="area-scan-entry"
        onClick={() => {
          setOpen(true);
          onOpen();
        }}
      >
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

      {planning && <p className="area-scan-hint" role="status">{t.areaScanPlanning}</p>}
      {geometry && plan && (
        <dl className="area-scan-plan" aria-label={t.areaScanSelectedArea}>
          <div><dt>{t.areaScanSelectedArea}</dt><dd>~ {plan.area_square_km} km²</dd></div>
          {plan.provider_queries !== null && (
            <div><dt>{t.areaScanEstimatedQueries}</dt><dd>{plan.provider_queries}</dd></div>
          )}
          <div><dt>{t.areaScanMaximumAllowed}</dt><dd>{plan.max_provider_queries}</dd></div>
        </dl>
      )}
      {plan?.reason === "too_large" && (
        <p className="area-scan-error" role="alert">{t.areaScanTooLargeShort}</p>
      )}

      {authenticated ? (
        <p className="area-scan-authenticated" role="status">
          {t.areaScanAuthenticated}
        </p>
      ) : operatorAuthenticationRequired ? (
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
      ) : authenticating ? (
        <p className="area-scan-authenticated" role="status">
          {t.areaScanAuthenticating}
        </p>
      ) : null}

      {result && (
        <dl className="area-scan-summary" aria-live="polite">
          <div><dt>{t.areaScanResults}</dt><dd>{result.total}</dd></div>
          <div><dt>{t.source}</dt><dd>{t.datalasticLiveAis}</dd></div>
          <div>
            <dt>{t.areaScanTime}</dt>
            <dd>{new Date(result.scanned_at).toLocaleString("en-US", {
              dateStyle: "medium",
              timeStyle: "short",
            })}</dd>
          </div>
          <div><dt>{t.areaScanQueries}</dt><dd>{result.scan.provider_queries}</dd></div>
          {categoryCounts.map(({ category, count }) => (
            <div key={category}><dt>{category}</dt><dd>{count}</dd></div>
          ))}
        </dl>
      )}
      {result?.cached && <span className="area-scan-cached">{t.areaScanCached}</span>}
      {error && <p className="area-scan-error" role="alert">{error}</p>}
      {providerRefreshAvailable && (
        <div className="area-scan-provider-recovery">
          <button
            type="button"
            disabled={!authenticated || providerRefreshing}
            onClick={onRefreshProvider}
          >
            {providerRefreshing ? t.providerStatusRefreshing : t.providerStatusRefresh}
          </button>
        </div>
      )}
      {providerRefreshMessage && (
        <p className="area-scan-hint" role="status">{providerRefreshMessage}</p>
      )}

      <div className="area-scan-actions">
        <button
          type="button"
          disabled={!canScan}
          onClick={onScan}
        >
          {loading ? t.areaScanning : result ? t.areaScanAgain : t.scanArea}
        </button>
        <button type="button" onClick={onClear}>
          {t.clearAreaScan}
        </button>
      </div>
    </aside>
  );
}
