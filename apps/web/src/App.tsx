import { useState } from "react";
import { Dashboard } from "./pages/Dashboard";
import { LiveDashboard } from "./pages/LiveDashboard";
import { LogisticsView } from "./features/logistics/LogisticsView";
import { LogisticsPanel } from "./features/logistics/LogisticsPanel";
import { I18nProvider, useI18n } from "./i18n/I18nContext";

/**
 * SeaWatch — Taiwan Maritime Awareness Platform.
 *
 * The live, bilingual, map-first Taiwan experience is the default product. The
 * original Phase 3B research dashboard remains available at ?research for
 * analysts who need the ranked review-candidate table. A top-level navigation
 * toggle switches between the LIVE MAP (SENSE/SURVIVE) and the RESILIENCE
 * LOGISTICS (RESPOND) view; the LiveDashboard is never altered by this toggle.
 */
function wantsResearch(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).has("research");
}

type View = "live" | "logistics";

function MainNav() {
  const { t } = useI18n();
  const L = t.logistics;
  const [view, setView] = useState<View>("live");

  return (
    <>
      <nav className="app-nav" aria-label="SeaWatch primary navigation">
        <button
          type="button"
          className={view === "live" ? "active" : ""}
          aria-pressed={view === "live"}
          onClick={() => setView("live")}
        >
          {L.navLiveMap}
        </button>
        <button
          type="button"
          className={view === "logistics" ? "active" : ""}
          aria-pressed={view === "logistics"}
          onClick={() => setView("logistics")}
        >
          {L.navLogistics}
        </button>
      </nav>
      {view === "live" ? (
        <LiveDashboard />
      ) : (
        <LogisticsView
          renderResult={({ context, brief }) => (
            <LogisticsPanel context={context} brief={brief} />
          )}
        />
      )}
    </>
  );
}

export default function App() {
  if (wantsResearch()) {
    return <Dashboard />;
  }
  return (
    <I18nProvider>
      <MainNav />
    </I18nProvider>
  );
}
