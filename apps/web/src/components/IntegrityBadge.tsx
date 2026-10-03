import { useI18n } from "../i18n/I18nContext";
import type { IntegrityKind } from "../lib/integrity";

const LABEL_KEY: Record<IntegrityKind, keyof ReturnType<typeof labels>> = {
  live: "badgeLiveAis",
  cached: "badgeCached",
  stale: "badgeStale",
  unknown: "valueUnknown",
  provider_interpolated: "badgeProviderInterpolated",
  visual_interpolation: "badgeVisualInterpolation",
  offline_demo: "badgeOfflineDemo",
};

function labels(t: ReturnType<typeof useI18n>["t"]) {
  return t;
}

/** A small, color-coded badge that names a data-integrity state. */
export function IntegrityBadge({ kind }: { kind: IntegrityKind }) {
  const { t } = useI18n();
  const key = LABEL_KEY[kind];
  return (
    <span className={`integrity-badge integrity-${kind}`} data-kind={kind}>
      {t[key] as string}
    </span>
  );
}
