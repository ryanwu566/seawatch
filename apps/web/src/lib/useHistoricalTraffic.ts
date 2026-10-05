import { useEffect, useState } from "react";
import { getHistoricalTraffic } from "../api/historicalTraffic";
import {
  buildHistoricalTrafficGeoJson,
  type HistoricalTrafficFeatureCollection,
} from "./historicalTraffic";

export interface HistoricalTrafficState {
  status: "loading" | "available" | "unavailable";
  data: HistoricalTrafficFeatureCollection | null;
}

export function useHistoricalTraffic(): HistoricalTrafficState {
  const [state, setState] = useState<HistoricalTrafficState>({
    status: "loading",
    data: null,
  });

  useEffect(() => {
    let active = true;
    getHistoricalTraffic()
      .then((response) => {
        if (!active) return;
        if (!response.available || !Array.isArray(response.cells) || response.cells.length === 0) {
          setState({ status: "unavailable", data: null });
          return;
        }
        setState({
          status: "available",
          data: buildHistoricalTrafficGeoJson(response.cells),
        });
      })
      .catch(() => {
        if (active) setState({ status: "unavailable", data: null });
      });
    return () => {
      active = false;
    };
  }, []);

  return state;
}
