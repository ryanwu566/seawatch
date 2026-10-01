import { Dashboard } from "./pages/Dashboard";
import { LiveDashboard } from "./pages/LiveDashboard";
import { I18nProvider } from "./i18n/I18nContext";

/**
 * SeaWatch — Taiwan Maritime Awareness Platform.
 *
 * The live, bilingual, map-first Taiwan experience is the default product. The
 * original Phase 3B research dashboard remains available at ?research for
 * analysts who need the ranked review-candidate table.
 */
function wantsResearch(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).has("research");
}

export default function App() {
  if (wantsResearch()) {
    return <Dashboard />;
  }
  return (
    <I18nProvider>
      <LiveDashboard />
    </I18nProvider>
  );
}
