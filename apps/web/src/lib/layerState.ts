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

// Default: keep the initial map simple. Live vessels + tracks + ports on;
// airspace and analysis overlays off until the user opts in.
export const DEFAULT_LAYER_STATE: LayerState = {
  baseMap: "nlsc-emap",
  liveVessels: true,
  vesselTracks: true,
  ports: true,
  navReference: false,
  restrictedAirspace: false,
  publicAirspace: false,
  reviewCandidates: false,
};
