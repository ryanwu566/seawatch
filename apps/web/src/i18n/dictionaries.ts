// Bilingual (Traditional Chinese default, English secondary) dictionary for the
// Taiwan Maritime Awareness Platform. Keys are stable identifiers; values are
// per-language strings. Components reference keys via the useI18n() hook so no
// JSX is duplicated per language.

export type Lang = "zh-Hant" | "en";

export const DEFAULT_LANG: Lang = "zh-Hant";

export interface Dict {
  // Product identity
  productName: string;
  productTagline: string;
  productSubtitle: string;

  // Header / status
  live: string;
  langToggleZh: string;
  langToggleEn: string;
  dataFreshness: string;
  vesselsNow: string;
  needsReview: string;
  lastUpdated: string;
  source: string;
  secondsAgo: (n: number) => string;
  minutesAgo: (n: number) => string;
  justNow: string;

  // Vessel panel
  vesselOverview: string;
  speed: string;
  course: string;
  heading: string;
  lastUpdate: string;
  recentTrack: string;
  reviewPriority: string;
  whyFlagged: string;
  knots: string;
  degrees: string;
  closePanel: string;
  selectVesselHint: string;
  buildingTrackHistory: string;
  collectingTrajectory: string;
  noVesselName: string;
  destination: string;

  // Advanced analysis
  advancedAnalysis: string;
  analysisMethod: string;
  percentile: string;
  supportingFeatures: string;
  dataQuality: string;
  benchmarkSource: string;
  benchmarkDisclaimer: string;

  // Layers
  layers: string;
  baseMaps: string;
  maritime: string;
  airspace: string;
  analysis: string;
  layerTaiwanEmap: string;
  layerOrthophoto: string;
  layerLiveVessels: string;
  layerVesselTracks: string;
  layerPorts: string;
  layerNavReference: string;
  layerRestrictedAirspace: string;
  layerPublicAirspace: string;
  layerReviewCandidates: string;

  // Data integrity badges
  badgeLiveAis: string;
  badgeCached: string;
  badgeStale: string;
  badgeProviderInterpolated: string;
  badgeVisualInterpolation: string;
  badgeOfflineDemo: string;
  measuredFix: string;
  visualPosition: string;

  // Offline
  offlineDemoData: string;
  offlineDemoNote: string;

  // Misc
  loading: string;
  errorLoadingVessels: string;
  attribution: string;
  corsNote: string;
}

const zhHant: Dict = {
  productName: "SeaWatch",
  productTagline: "臺灣海域智慧態勢平台",
  productSubtitle: "Taiwan Maritime Awareness Platform",

  live: "即時資料",
  langToggleZh: "中文",
  langToggleEn: "EN",
  dataFreshness: "資料更新",
  vesselsNow: "目前船舶",
  needsReview: "需關注",
  lastUpdated: "資料更新",
  source: "資料來源",
  secondsAgo: (n) => `${n} 秒前`,
  minutesAgo: (n) => `${n} 分鐘前`,
  justNow: "剛剛",

  vesselOverview: "船舶概況",
  speed: "目前航速",
  course: "航向",
  heading: "船首向",
  lastUpdate: "最近更新",
  recentTrack: "最近航跡",
  reviewPriority: "關注程度",
  whyFlagged: "為什麼值得注意",
  knots: "節",
  degrees: "度",
  closePanel: "關閉",
  selectVesselHint: "點選地圖上的船舶以查看詳細資訊",
  buildingTrackHistory: "航跡累積中",
  collectingTrajectory: "資料累積中",
  noVesselName: "未提供船名",
  destination: "目的地",

  advancedAnalysis: "進階分析",
  analysisMethod: "分析方法",
  percentile: "百分位",
  supportingFeatures: "判斷依據",
  dataQuality: "資料品質",
  benchmarkSource: "基準資料來源",
  benchmarkDisclaimer:
    "分析模型以 NOAA 舊金山灣歷史 AIS 為基準，尚未經臺灣海域驗證，僅供人工參考。",

  layers: "圖層",
  baseMaps: "底圖",
  maritime: "海事圖層",
  airspace: "空域圖層",
  analysis: "分析",
  layerTaiwanEmap: "臺灣通用電子地圖",
  layerOrthophoto: "正射影像",
  layerLiveVessels: "即時船舶",
  layerVesselTracks: "船舶航跡",
  layerPorts: "商港",
  layerNavReference: "海事參考",
  layerRestrictedAirspace: "禁航／限航區",
  layerPublicAirspace: "公開空域資訊",
  layerReviewCandidates: "需關注船舶",

  badgeLiveAis: "即時 AIS",
  badgeCached: "快取",
  badgeStale: "資料較舊",
  badgeProviderInterpolated: "供應商插值",
  badgeVisualInterpolation: "視覺平滑",
  badgeOfflineDemo: "離線展示",
  measuredFix: "實際 AIS 定位",
  visualPosition: "視覺平滑位置",

  offlineDemoData: "離線展示資料",
  offlineDemoNote: "目前顯示離線展示資料，並非即時 AIS。",

  loading: "載入中…",
  errorLoadingVessels: "無法載入即時船舶資料",
  attribution: "資料來源：Open Waters AIS",
  corsNote: "官方圖資因瀏覽器 CORS 限制無法載入時，將顯示此註記。",
};

const en: Dict = {
  productName: "SeaWatch",
  productTagline: "Taiwan Maritime Awareness Platform",
  productSubtitle: "臺灣海域智慧態勢平台",

  live: "LIVE",
  langToggleZh: "中文",
  langToggleEn: "EN",
  dataFreshness: "Data freshness",
  vesselsNow: "Vessels Now",
  needsReview: "Needs Review",
  lastUpdated: "Last Updated",
  source: "Source",
  secondsAgo: (n) => `${n} sec ago`,
  minutesAgo: (n) => `${n} min ago`,
  justNow: "just now",

  vesselOverview: "Vessel Overview",
  speed: "Speed",
  course: "Course",
  heading: "Heading",
  lastUpdate: "Last Update",
  recentTrack: "Recent Track",
  reviewPriority: "Review Priority",
  whyFlagged: "Why It Was Flagged",
  knots: "kn",
  degrees: "°",
  closePanel: "Close",
  selectVesselHint: "Click a vessel on the map to see details",
  buildingTrackHistory: "Building Track History",
  collectingTrajectory: "Collecting trajectory",
  noVesselName: "Name not provided",
  destination: "Destination",

  advancedAnalysis: "Advanced Analysis",
  analysisMethod: "Analysis Method",
  percentile: "Percentile",
  supportingFeatures: "Supporting Evidence",
  dataQuality: "Data Quality",
  benchmarkSource: "Benchmark Source",
  benchmarkDisclaimer:
    "The analysis model is benchmarked on NOAA San Francisco Bay historical AIS and is NOT Taiwan-validated. For human review only.",

  layers: "Layers",
  baseMaps: "Base Maps",
  maritime: "Maritime Layers",
  airspace: "Airspace Layers",
  analysis: "Analysis",
  layerTaiwanEmap: "Taiwan e-Map",
  layerOrthophoto: "Orthophoto",
  layerLiveVessels: "Live Vessels",
  layerVesselTracks: "Vessel Tracks",
  layerPorts: "Commercial Ports",
  layerNavReference: "Navigation Reference",
  layerRestrictedAirspace: "Prohibited / Restricted",
  layerPublicAirspace: "Public Airspace Info",
  layerReviewCandidates: "Vessels to Review",

  badgeLiveAis: "Live AIS",
  badgeCached: "Cached",
  badgeStale: "Stale",
  badgeProviderInterpolated: "Provider Interpolated",
  badgeVisualInterpolation: "Visual Interpolation",
  badgeOfflineDemo: "Offline Demo",
  measuredFix: "Measured AIS Fix",
  visualPosition: "Visual Interpolation",

  offlineDemoData: "Offline Demo Data",
  offlineDemoNote: "Showing offline demo data — this is not live AIS.",

  loading: "Loading…",
  errorLoadingVessels: "Failed to load live vessels",
  attribution: "Source: Open Waters AIS",
  corsNote:
    "If an official map layer is blocked by browser CORS, this note is shown instead of faking success.",
};

export const DICTIONARIES: Record<Lang, Dict> = {
  "zh-Hant": zhHant,
  en,
};
