import { useI18n } from "../i18n/I18nContext";
import type { ModePresentation } from "../lib/resilience";

interface AppHeaderProps {
  presentation: ModePresentation;
}

/** Product header: identity, status indicator, instant language toggle. */
export function AppHeader({ presentation }: AppHeaderProps) {
  const { t, lang, toggleLang } = useI18n();

  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-name">{t.productName}</span>
        <span className="brand-tagline">{t.productTagline}</span>
        <span className="brand-sub">{t.productSubtitle}</span>
      </div>
      <div className="header-right">
        <span
          className={`live-pill live-${presentation.mode.toLowerCase()}`}
          title={presentation.detail || presentation.coverageLabel}
          data-status={presentation.mode}
        >
          <span className="live-dot" /> {presentation.label}
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
