import { useState } from "react";
import { useI18n } from "../i18n/I18nContext";
import type { LayerState } from "../lib/layerState";

interface LayerControlProps {
  layers: LayerState;
  onChange: (next: LayerState) => void;
}

/** Friendly grouped layer control: Base Maps / Maritime / Airspace / Analysis. */
export function LayerControl({ layers, onChange }: LayerControlProps) {
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
