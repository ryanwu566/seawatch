import type { OperatingMode, ResilienceStatus } from "../api/live";
import { useI18n } from "../i18n/I18nContext";
import { transitionEvent } from "../lib/resilience";

export function ResilienceBanner({
  status,
  previousMode,
}: {
  status: ResilienceStatus;
  previousMode: OperatingMode | null;
}) {
  const { t } = useI18n();
  const event = transitionEvent(previousMode, status);
  if (!event) return null;
  const message = event.kind === "cloud_to_edge" ? t.cloudToEdge : t.cloudRestored;
  return (
    <div className="resilience-banner" role="status" data-transition={event.kind}>
      {event.simulated ? `${t.simulatedPrefix}: ` : ""}
      {message}
    </div>
  );
}
