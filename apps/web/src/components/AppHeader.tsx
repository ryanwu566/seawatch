import { useI18n } from "../i18n/I18nContext";

interface AppHeaderProps {
  status: "online" | "degraded" | "offline";
  demo: boolean;
}

/** Product header: identity, LIVE indicator, instant language toggle. */
export function AppHeader({ status, demo }: AppHeaderProps) {
  const { t, lang, toggleLang } = useI18n();
  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-name">{t.productName}</span>
        <span className="brand-tagline">{t.productTagline}</span>
        <span className="brand-sub">{t.productSubtitle}</span>
      </div>
      <div className="header-right">
        {demo ? (
          <span className="live-pill demo" title={t.offlineDemoNote}>
            {t.offlineDemoData}
          </span>
        ) : (
          <span className={`live-pill live-${status}`}>
            <span className="live-dot" /> {t.live}
          </span>
        )}
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
