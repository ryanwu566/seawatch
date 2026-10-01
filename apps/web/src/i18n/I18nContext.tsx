import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { DEFAULT_LANG, DICTIONARIES, type Dict, type Lang } from "./dictionaries";

interface I18nContextValue {
  lang: Lang;
  t: Dict;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

const STORAGE_KEY = "seawatch.lang";

function readInitialLang(): Lang {
  if (typeof window === "undefined") return DEFAULT_LANG;
  const stored = window.localStorage?.getItem(STORAGE_KEY);
  return stored === "en" || stored === "zh-Hant" ? stored : DEFAULT_LANG;
}

/**
 * Provides the active language and its dictionary. Switching language updates
 * state in place (no page reload) and persists the preference.
 */
export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    if (typeof window !== "undefined") {
      window.localStorage?.setItem(STORAGE_KEY, next);
      document.documentElement.lang = next === "zh-Hant" ? "zh-Hant" : "en";
    }
  }, []);

  const toggleLang = useCallback(() => {
    setLangState((prev) => {
      const next: Lang = prev === "zh-Hant" ? "en" : "zh-Hant";
      if (typeof window !== "undefined") {
        window.localStorage?.setItem(STORAGE_KEY, next);
        document.documentElement.lang = next === "zh-Hant" ? "zh-Hant" : "en";
      }
      return next;
    });
  }, []);

  const value = useMemo<I18nContextValue>(
    () => ({ lang, t: DICTIONARIES[lang], setLang, toggleLang }),
    [lang, setLang, toggleLang],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    throw new Error("useI18n must be used within an I18nProvider");
  }
  return ctx;
}
