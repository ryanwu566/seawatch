// Layer visibility state shared between the layer control and the map canvas.

import type { BaseMapId } from "../config/taiwanMap";

export interface LayerState {
  baseMap: BaseMapId;
  liveVessels: boolean;
  vesselTracks: boolean;
  ports: boolean;
  navReference: boolean;
  restrictedAirspace: boolean;
  publicAirspace: boolean;
  reviewCandidates: boolean;
}

// Default live-mode state: the map must not look empty, so live vessels are ON.
// Commercial ports are ON for geographic context. Vessel trails stay OFF until a
// vessel is selected (the selected vessel's trail is shown regardless of this
// toggle). Airspace and analysis overlays are OFF until the user opts in.
export const DEFAULT_LAYER_STATE: LayerState = {
  baseMap: "nlsc-emap",
  liveVessels: true,
  vesselTracks: false,
  ports: true,
  navReference: false,
  restrictedAirspace: false,
  publicAirspace: false,
  reviewCandidates: false,
};
