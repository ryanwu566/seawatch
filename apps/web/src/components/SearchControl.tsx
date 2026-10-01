import { useMemo, useState } from "react";
import { useI18n } from "../i18n/I18nContext";
import type { LiveVesselFeature } from "../api/live";
import {
  COMMERCIAL_PORTS,
  LOCATION_PRESETS,
  type LocationPreset,
} from "../config/taiwanMap";

interface SearchControlProps {
  vessels: LiveVesselFeature[];
  onSelectVessel: (vessel: LiveVesselFeature) => void;
  onFitBounds: (bounds: [number, number, number, number]) => void;
}

interface VesselResult {
  kind: "vessel";
  id: string;
  label: string;
  sub: string;
  vessel: LiveVesselFeature;
}
interface PortResult {
  kind: "port";
  id: string;
  label: string;
  sub: string;
  bounds: [number, number, number, number];
}
type Result = VesselResult | PortResult;

const MAX_RESULTS = 8;

/**
 * FlightRadar24-style search: filters currently-loaded vessels by name or
 * destination and offers commercial ports + quick-location presets. No backend
 * search endpoint is used; this searches the in-memory viewport feed only.
 */
export function SearchControl({ vessels, onSelectVessel, onFitBounds }: SearchControlProps) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);

  const results = useMemo<Result[]>(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    const vesselHits: Result[] = vessels
      .filter((v) => {
        const name = (v.properties.name ?? "").toLowerCase();
        const dest = (v.properties.destination ?? "").toLowerCase();
        return name.includes(q) || dest.includes(q);
      })
      .slice(0, MAX_RESULTS)
      .map((v) => ({
        kind: "vessel" as const,
        id: v.id,
        label: v.properties.name || t.noVesselName,
        sub: v.properties.destination ? `→ ${v.properties.destination}` : t.searchVessels,
        vessel: v,
      }));
    const portHits: Result[] = COMMERCIAL_PORTS.filter(
      (p) => p.nameZh.toLowerCase().includes(q) || p.nameEn.toLowerCase().includes(q),
    )
      .slice(0, MAX_RESULTS)
      .map((p) => ({
        kind: "port" as const,
        id: p.id,
        label: `${p.nameZh} / ${p.nameEn}`,
        sub: t.searchPorts,
        // A small sea-facing box around the port.
        bounds: [p.lon - 0.25, p.lat - 0.2, p.lon + 0.25, p.lat + 0.2],
      }));
    return [...vesselHits, ...portHits].slice(0, MAX_RESULTS);
  }, [query, vessels, t]);

  const choose = (r: Result) => {
    if (r.kind === "vessel") {
      onSelectVessel(r.vessel);
    } else {
      onFitBounds(r.bounds);
    }
    setQuery("");
    setFocused(false);
  };

  const choosePreset = (preset: LocationPreset) => {
    onFitBounds(preset.bounds);
  };

  const showResults = focused && query.trim().length > 0;

  return (
    <div className="search-control">
      <div className="search-box">
        <span className="search-icon" aria-hidden="true">
          ⌕
        </span>
        <input
          type="search"
          className="search-input"
          placeholder={t.searchPlaceholder}
          aria-label={t.searchPlaceholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => window.setTimeout(() => setFocused(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results.length > 0) choose(results[0]);
            if (e.key === "Escape") {
              setQuery("");
              setFocused(false);
            }
          }}
        />
      </div>

      {showResults && (
        <ul className="search-results" role="listbox" aria-label={t.searchPlaceholder}>
          {results.length === 0 ? (
            <li className="search-empty">{t.searchNoResults}</li>
          ) : (
            results.map((r) => (
              <li key={`${r.kind}-${r.id}`}>
                <button
                  type="button"
                  className="search-result"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => choose(r)}
                >
                  <span className={`result-kind result-${r.kind}`} aria-hidden="true">
                    {r.kind === "vessel" ? "⛟" : "⚓"}
                  </span>
                  <span className="result-text">
                    <span className="result-label">{r.label}</span>
                    <span className="result-sub">{r.sub}</span>
                  </span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}

      <div className="preset-row" role="group" aria-label={t.presetsLabel}>
        {LOCATION_PRESETS.map((preset) => (
          <button
            key={preset.id}
            type="button"
            className="preset-btn"
            onClick={() => choosePreset(preset)}
          >
            {t[preset.labelKey]}
          </button>
        ))}
      </div>
    </div>
  );
}
