import { Dashboard } from "./pages/Dashboard";
import { LiveMap } from "./components/LiveMap";

/**
 * Temporary Live Taiwan mode switch (Phase 7A proof).
 *
 * Visit the app with ?live to see real-time Taiwan AIS vessels drawn from the
 * SeaWatch backend's /live endpoints. The full bilingual redesign comes later;
 * this is only the minimal proof that REAL Taiwan ships appear on the map.
 */
function isLiveMode(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).has("live");
}

export default function App() {
  if (isLiveMode()) {
    return <LiveMap />;
  }
  return <Dashboard />;
}
