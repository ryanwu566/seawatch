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
  reconnecting: string;
  staleData: string;
  liveSourceLabel: string;
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
  vesselType: string;
  positionStatus: string;
  positionMeasured: string;
  positionProviderInterp: string;
  positionStale: string;
  noRecentUpdate: string;

  // Follow mode
  followVessel: string;
  resumeFollow: string;
  following: string;

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

  // Search + presets
  searchPlaceholder: string;
  searchVessels: string;
  searchPorts: string;
  searchNoResults: string;
  presetTaiwanWaters: string;
  presetKeelung: string;
  presetTaiwanStrait: string;
  presetKaohsiung: string;
  presetsLabel: string;

  // Empty / error / reconnecting states
  emptyViewport: string;
  showNearbyVessels: string;
  reconnectingAis: string;
  collectingForAnalysis: string;
  illustrativeAirspace: string;

  // Misc
  loading: string;
  errorLoadingVessels: string;
  attribution: string;
  corsNote: string;
  openLayers: string;
  statusLabel: string;

  // Phase 8 resilience modes
  modeCloud: string;
  modeEdge: string;
  modeReplay: string;
  modeNoSource: string;
  modeDemo: string;
  coverageCloud: string;
  coverageEdge: string;
  coverageNone: string;
  coverageDemo: string;
  edgeCoverageNote: string;
  replayRecordedNote: string;
  externalPower: string;
  batteryUps: string;
  powerRequirement: string;
  cloudToEdge: string;
  cloudRestored: string;
  simulatedPrefix: string;

  // Phase 9 resilience logistics (RESPOND)
  logistics: LogisticsDict;
}

/** Phase 9 Resilience Logistics bilingual strings (additive, self-contained). */
export interface LogisticsDict {
  navLiveMap: string;
  navLogistics: string;
  title: string;
  subtitle: string;
  scenarioLabel: string;
  selectScenario: string;
  disruptedPort: string;
  criticalDemand: string;
  priority: string;
  alternatives: string;
  runSimulation: string;
  running: string;
  recommendedAllocation: string;
  decisionBrief: string;
  tradeOffs: string;
  unmetDemand: string;
  noUnmetDemand: string;
  colPort: string;
  colEta: string;
  colDistance: string;
  colCost: string;
  colCapacity: string;
  colRisk: string;
  colUnits: string;
  etaHours: string;
  distanceKm: string;
  capacityUnits: string;
  truthBadgeTitle: string;
  schematicConnector: string;
  assumptions: string;
  loadError: string;
  commodityMedical: string;
  commodityFood: string;
  commodityFuel: string;
  contextEdgeBanner: string;
}

const zhHant: Dict = {
  productName: "SeaWatch",
  productTagline: "臺灣海域智慧態勢平台",
  productSubtitle: "Taiwan Maritime Awareness Platform",

  live: "即時 AIS",
  reconnecting: "重新連線中",
  staleData: "資料較舊",
  liveSourceLabel: "即時 AIS",
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
  noVesselName: "未公開船名",
  destination: "目的地",
  vesselType: "船舶類型",
  positionStatus: "位置狀態",
  positionMeasured: "實際 AIS",
  positionProviderInterp: "供應商插值",
  positionStale: "資料較舊",
  noRecentUpdate: "此船舶暫時沒有新資料",

  followVessel: "追蹤船舶",
  resumeFollow: "繼續追蹤",
  following: "追蹤中",

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

  searchPlaceholder: "搜尋船舶或港口",
  searchVessels: "船舶",
  searchPorts: "港口",
  searchNoResults: "找不到符合的結果",
  presetTaiwanWaters: "臺灣海域",
  presetKeelung: "基隆",
  presetTaiwanStrait: "臺灣海峽",
  presetKaohsiung: "高雄",
  presetsLabel: "快速定位",

  emptyViewport: "此區域目前沒有船舶資料",
  showNearbyVessels: "顯示附近船舶",
  reconnectingAis: "正在重新取得即時 AIS…",
  collectingForAnalysis: "分析資料累積中",
  illustrativeAirspace: "示意空域",

  loading: "載入中…",
  errorLoadingVessels: "無法載入即時船舶資料",
  attribution: "資料來源：Open Waters AIS",
  corsNote: "官方圖資因瀏覽器 CORS 限制無法載入時，將顯示此註記。",
  openLayers: "開啟圖層選單",
  statusLabel: "即時狀態",
  modeCloud: "雲端即時 AIS",
  modeEdge: "本地 AIS 接收",
  modeReplay: "本地接收重播",
  modeNoSource: "即時資料無法使用",
  modeDemo: "離線示範資料",
  coverageCloud: "臺灣廣域網路 AIS",
  coverageEdge: "本地無線電 AIS",
  coverageNone: "無即時涵蓋",
  coverageDemo: "示範資料",
  edgeCoverageNote: "僅顯示本地天線可接收的船舶。",
  replayRecordedNote: "此為錄製資料，非即時無線電 AIS。",
  externalPower: "外部電源",
  batteryUps: "電池／UPS",
  powerRequirement: "韌性運作需要筆電電池或 UPS。",
  cloudToEdge: "雲端 AIS 無法使用，已切換至本地 AIS 接收器",
  cloudRestored: "雲端 AIS 已恢復",
  simulatedPrefix: "模擬",

  logistics: {
    navLiveMap: "即時地圖",
    navLogistics: "韌性物流",
    title: "韌性物流決策支援",
    subtitle: "民用港口中斷情境的規劃估計值，供人工審查，並非指示或預測。",
    scenarioLabel: "情境",
    selectScenario: "選擇情境",
    disruptedPort: "中斷港口",
    criticalDemand: "關鍵民生需求",
    priority: "優先序",
    alternatives: "替代港口",
    runSimulation: "執行模擬",
    running: "模擬中…",
    recommendedAllocation: "建議配置",
    decisionBrief: "決策摘要",
    tradeOffs: "權衡取捨",
    unmetDemand: "未滿足需求",
    noUnmetDemand: "在此情境資料集內所有需求皆可滿足。",
    colPort: "港口",
    colEta: "預估抵達",
    colDistance: "距離",
    colCost: "相對成本",
    colCapacity: "容量使用",
    colRisk: "風險",
    colUnits: "單位",
    etaHours: "小時",
    distanceKm: "公里",
    capacityUnits: "單位/日",
    truthBadgeTitle: "資料來源說明",
    schematicConnector: "示意連線（SCHEMATIC CONNECTOR）",
    assumptions: "假設",
    loadError: "無法載入物流情境資料。",
    commodityMedical: "醫療",
    commodityFood: "食品",
    commodityFuel: "燃料",
    contextEdgeBanner: "目前為邊緣模式——物流使用本地情境資料集。",
  },
};

const en: Dict = {
  productName: "SeaWatch",
  productTagline: "Taiwan Maritime Awareness Platform",
  productSubtitle: "臺灣海域智慧態勢平台",

  live: "LIVE",
  reconnecting: "Reconnecting",
  staleData: "Stale Data",
  liveSourceLabel: "Live AIS",
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
  noVesselName: "Name not disclosed",
  destination: "Destination",
  vesselType: "Vessel Type",
  positionStatus: "Position status",
  positionMeasured: "Measured AIS",
  positionProviderInterp: "Provider Interpolated",
  positionStale: "Stale Data",
  noRecentUpdate: "No recent update for this vessel",

  followVessel: "Follow vessel",
  resumeFollow: "Resume Follow",
  following: "Following",

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

  searchPlaceholder: "Search vessels or ports",
  searchVessels: "Vessels",
  searchPorts: "Ports",
  searchNoResults: "No matching results",
  presetTaiwanWaters: "Taiwan Waters",
  presetKeelung: "Keelung",
  presetTaiwanStrait: "Taiwan Strait",
  presetKaohsiung: "Kaohsiung",
  presetsLabel: "Quick locations",

  emptyViewport: "No vessel data in this area right now",
  showNearbyVessels: "Show nearby vessels",
  reconnectingAis: "Reacquiring live AIS…",
  collectingForAnalysis: "Collecting data for analysis",
  illustrativeAirspace: "Illustrative Airspace",

  loading: "Loading…",
  errorLoadingVessels: "Failed to load live vessels",
  attribution: "Source: Open Waters AIS",
  corsNote:
    "If an official map layer is blocked by browser CORS, this note is shown instead of faking success.",
  openLayers: "Open layer menu",
  statusLabel: "Live status",
  modeCloud: "CLOUD LIVE",
  modeEdge: "EDGE LIVE",
  modeReplay: "EDGE REPLAY",
  modeNoSource: "LIVE DATA UNAVAILABLE",
  modeDemo: "OFFLINE DEMO",
  coverageCloud: "Taiwan-wide network AIS",
  coverageEdge: "Local RF AIS",
  coverageNone: "No live coverage",
  coverageDemo: "Demo data",
  edgeCoverageNote: "Shows only vessels receivable by the local antenna.",
  replayRecordedNote: "Recorded data — not live RF AIS.",
  externalPower: "External Power",
  batteryUps: "Battery / UPS",
  powerRequirement: "Power resilience requires laptop battery or UPS.",
  cloudToEdge: "Cloud AIS unavailable — switched to local AIS receiver",
  cloudRestored: "Cloud AIS restored",
  simulatedPrefix: "SIMULATED",

  logistics: {
    navLiveMap: "LIVE MAP",
    navLogistics: "RESILIENCE LOGISTICS",
    title: "Resilience Logistics Decision Support",
    subtitle:
      "Scenario-based planning estimates for a civilian port disruption, for human review — not an instruction or a prediction.",
    scenarioLabel: "Scenario",
    selectScenario: "Select a scenario",
    disruptedPort: "Disrupted port",
    criticalDemand: "Critical civilian demand",
    priority: "priority",
    alternatives: "Alternative ports",
    runSimulation: "Run Simulation",
    running: "Running…",
    recommendedAllocation: "Recommended allocation",
    decisionBrief: "Decision brief",
    tradeOffs: "Trade-offs",
    unmetDemand: "Unmet demand",
    noUnmetDemand: "All demand satisfied within this scenario dataset.",
    colPort: "Port",
    colEta: "ETA",
    colDistance: "Distance",
    colCost: "Relative cost",
    colCapacity: "Capacity use",
    colRisk: "Risk",
    colUnits: "Units",
    etaHours: "h",
    distanceKm: "km",
    capacityUnits: "units/day",
    truthBadgeTitle: "Data provenance",
    schematicConnector: "SCHEMATIC CONNECTOR / 示意連線",
    assumptions: "Assumptions",
    loadError: "Failed to load logistics scenario data.",
    commodityMedical: "Medical",
    commodityFood: "Food",
    commodityFuel: "Fuel",
    contextEdgeBanner: "Running in Edge mode — logistics uses the local scenario dataset.",
  },
};

export const DICTIONARIES: Record<Lang, Dict> = {
  "zh-Hant": zhHant,
  en,
};
