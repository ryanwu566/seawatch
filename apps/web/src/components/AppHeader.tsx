import { useI18n } from "../i18n/I18nContext";
import type { LiveStatusKind } from "../lib/liveStatus";

interface AppHeaderProps {
  /** Derived from real /live/health (plus demo flag), not just the env flag. */
  status: LiveStatusKind;
}

/** Product header: identity, status indicator, instant language toggle. */
export function AppHeader({ status }: AppHeaderProps) {
  const { t, lang, toggleLang } = useI18n();

  const label =
    status === "offline_demo"
      ? t.offlineDemoData
      : status === "reconnecting"
        ? t.reconnecting
        : status === "stale"
          ? t.staleData
          : t.live;

  const title = status === "offline_demo" ? t.offlineDemoNote : undefined;

  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-name">{t.productName}</span>
        <span className="brand-tagline">{t.productTagline}</span>
        <span className="brand-sub">{t.productSubtitle}</span>
      </div>
      <div className="header-right">
        <span className={`live-pill live-${status}`} title={title} data-status={status}>
          {status !== "offline_demo" && <span className="live-dot" />} {label}
        </span>
        <button
          type="button"
          className="lang-toggle"
          onClick={toggleLang}
          aria-label="Toggle language"
        >
          <span className={lang === "zh-Hant" ? "active" : ""}>{t.langToggleZh}</span>
          <span className="sep">|</span>
          <span className={lang === "en" ? "active" : ""}>{t.langToggleEn}</span>
        </button>
      </div>
    </header>
  );
}
