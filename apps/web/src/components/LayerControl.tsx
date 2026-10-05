import { useState } from "react";
import { useI18n } from "../i18n/I18nContext";
import type { LayerState } from "../lib/layerState";

interface LayerControlProps {
  layers: LayerState;
  onChange: (next: LayerState) => void;
  historicalTrafficAvailable?: boolean;
}

/** Friendly grouped layer control: Base Maps / Maritime / Airspace / Analysis. */
export function LayerControl({
  layers,
  onChange,
  historicalTrafficAvailable,
}: LayerControlProps) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  const toggle = (key: keyof LayerState) => (e: React.ChangeEvent<HTMLInputElement>) =>
    onChange({ ...layers, [key]: e.target.checked });

  return (
    <div className={`layer-control ${open ? "open" : ""}`}>
      <button
        type="button"
        className="layer-control-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={t.openLayers}
      >
        {t.layers}
      </button>
      {open && (
        <div className="layer-control-panel" role="group" aria-label={t.layers}>
          <fieldset>
            <legend>{t.baseMaps}</legend>
            <label>
              <input
                type="radio"
                name="basemap"
                checked={layers.baseMap === "nlsc-emap"}
                onChange={() => onChange({ ...layers, baseMap: "nlsc-emap" })}
              />
              {t.layerTaiwanEmap}
            </label>
            <label>
              <input
                type="radio"
                name="basemap"
                checked={layers.baseMap === "nlsc-photo"}
                onChange={() => onChange({ ...layers, baseMap: "nlsc-photo" })}
              />
              {t.layerOrthophoto}
            </label>
          </fieldset>

          <fieldset>
            <legend>{t.maritime}</legend>
            <label>
              <input type="checkbox" checked={layers.liveVessels} onChange={toggle("liveVessels")} />
              {t.layerLiveVessels}
            </label>
            <label>
              <input type="checkbox" checked={layers.vesselTracks} onChange={toggle("vesselTracks")} />
              {t.layerVesselTracks}
            </label>
            <label>
              <input type="checkbox" checked={layers.ports} onChange={toggle("ports")} />
              {t.layerPorts}
            </label>
          </fieldset>

          <fieldset>
            <legend>{t.maritimeBoundaries}</legend>
            <label>
              <input
                type="checkbox"
                checked={layers.eezReference}
                onChange={toggle("eezReference")}
              />
              {t.layerEezReference}
            </label>
            <label>
              <input
                type="checkbox"
                checked={layers.territorialSea12NmReference}
                onChange={toggle("territorialSea12NmReference")}
              />
              <span>
                {t.layerTerritorialSea12NmReference}
                <span className="layer-note layer-note-block">{t.derivedReferencePolygon}</span>
              </span>
            </label>
            <label>
              <input
                type="checkbox"
                checked={layers.contiguousZone24NmReference}
                onChange={toggle("contiguousZone24NmReference")}
              />
              <span>
                {t.layerContiguousZone24NmReference}
                <span className="layer-note layer-note-block">{t.derivedReferenceBand}</span>
              </span>
            </label>
            <p className="layer-note maritime-reference-note">{t.maritimeReferenceCaveat}</p>
          </fieldset>

          <fieldset>
            <legend>{t.airspace}</legend>
            <label>
              <input
                type="checkbox"
                checked={layers.publicAirspace}
                onChange={toggle("publicAirspace")}
              />
              {t.layerPublicAirspace}
              <span className="layer-note">({t.illustrativeAirspace})</span>
            </label>
          </fieldset>

          <fieldset>
            <legend>{t.analysis}</legend>
            <label>
              <input
                type="checkbox"
                checked={layers.historicalTraffic}
                disabled={historicalTrafficAvailable !== true}
                onChange={toggle("historicalTraffic")}
              />
              <span>
                Historical Traffic Density
                {historicalTrafficAvailable === false && (
                  <span className="layer-note layer-note-block">
                    Historical traffic unavailable
                  </span>
                )}
                {historicalTrafficAvailable === undefined && (
                  <span className="layer-note layer-note-block">
                    Loading historical traffic
                  </span>
                )}
              </span>
            </label>
            <label>
              <input
                type="checkbox"
                checked={layers.reviewCandidates}
                onChange={toggle("reviewCandidates")}
              />
              {t.layerReviewCandidates}
            </label>
          </fieldset>
        </div>
      )}
    </div>
  );
}
