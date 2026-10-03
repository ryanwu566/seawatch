// Friendly, non-technical display helpers for the public UI.

import type { Dict } from "../i18n/dictionaries";

/**
 * Map a raw provider id to a friendly, bilingual source label. The raw id is
 * only ever shown under advanced/debug info, never in the main UI.
 */
export function friendlySource(providerId: string, t: Dict): string {
  // All live data currently comes from the Open Waters AIS feed. The friendly
  // label follows the active language (即時 AIS / Live AIS).
  return providerId === "datalastic" ? t.datalasticLiveAis : t.liveSourceLabel;
}

/** The attribution line always names the real upstream feed. */
export const OPEN_WATERS_LABEL = "Open Waters AIS";

// Coarse AIS ship-type buckets (first digit of the AIS type code). Only broad,
// public categories — no classification beyond what the AIS type field states.
export function vesselTypeLabel(code: number | null, lang: "zh-Hant" | "en"): string {
  if (code === null || !Number.isFinite(code)) return lang === "zh-Hant" ? "未分類" : "Unclassified";
  const bucket = Math.floor(code / 10);
  const zh: Record<number, string> = {
    2: "特種船舶",
    3: "作業船舶",
    4: "高速船",
    5: "特殊用途",
    6: "客船",
    7: "貨船",
    8: "油輪／液貨船",
    9: "其他",
  };
  const en: Record<number, string> = {
    2: "Wing-in-ground",
    3: "Special craft",
    4: "High-speed craft",
    5: "Special purpose",
    6: "Passenger",
    7: "Cargo",
    8: "Tanker",
    9: "Other",
  };
  const table = lang === "zh-Hant" ? zh : en;
  return table[bucket] ?? (lang === "zh-Hant" ? "其他" : "Other");
}
