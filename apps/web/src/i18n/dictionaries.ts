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

  // Vessel Intelligence Card (explainable, human-in-the-loop review support)
  intelligenceTitle: string;
  intelligenceIdentity: string;
  intelligenceName: string;
  intelligenceType: string;
  intelligenceFlag: string;
  intelligenceImo: string;
  intelligenceBehavior: string;
  intelligenceObservations: string;
  intelligenceSessionSpan: string;
  intelligenceTypicalRoute: string;
  intelligenceUsualArea: string;
  intelligenceReviewNotes: string;
  intelligenceNoReasons: string;
  intelligenceNoBaseline: string;
  intelligenceHumanReview: string;
  intelligenceReasonLoitering: string;
  intelligenceReasonSpeedChange: string;
  intelligenceReasonCourseChange: string;
  intelligenceThisSession: string;
  provenanceOfficial: string;
  provenanceObserved: string;
  provenanceDerived: string;
  provenanceUnknown: string;
  valueUnknown: string;

  // Route Deviation evidence (route-deviation-1)
  routeDeviationTitle: string;
  routeDeviationStatus: string;
  routeDeviationDetected: string;
  routeWithinCorridor: string;
  routeDeviationDistance: string;
  routeDeviationBaseline: string;
  routeDeviationConfidence: string;
  routeDeviationSource: string;
  routeDeviationExplanation: string;
  routeDeviationUnknown: string;
  confidenceHigh: string;
  confidenceMedium: string;
  confidenceLow: string;

  // Maritime GIS context (gis-context-1)
  gisContextTitle: string;
  gisDistanceToCoast: string;
  gisNearestPort: string;
  gisDistanceToPort: string;
  gisMaritimeArea: string;
  gisNotWithinArea: string;
  gisOutsideCoverage: string;

  // Historical GFW baseline
  historicalBaselineTitle: string;
  historicalObservedDays: string;
  historicalObservations: string;
  historicalTracks: string;
  historicalMovementCorridor: string;
  historicalBaselineAvailable: string;
  historicalCorridorAvailable: string;
  historicalInsufficient: string;
  historicalNotFound: string;
  historicalUnavailable: string;
  historicalGfwSource: string;

  // Satellite evidence
  satelliteEvidenceTitle: string;
  satelliteAvailability: string;
  satelliteProvider: string;
  satelliteSceneId: string;
  satellitePlatform: string;
  satelliteObservedDatetime: string;
  satelliteOrbit: string;

  // DEMO fixture (frontend-only, illustrative)
  demoIllustrativeLabel: string;
  demoViewVessel: string;
  demoPositionStatus: string;
  demoSourceLabel: string;

  // Explicit Datalastic Area Scan
  areaScan: string;
  areaScanPolygon: string;
  areaScanRectangle: string;
  areaScanDrawHint: string;
  areaScanReady: string;
  areaScanOperatorCredential: string;
  areaScanOperatorCredentialHint: string;
  areaScanAuthenticate: string;
  areaScanAuthenticating: string;
  areaScanAuthenticated: string;
  areaScanAuthFailed: string;
  areaScanSessionExpired: string;
  scanArea: string;
  clearAreaScan: string;
  areaScanning: string;
  areaScanResults: string;
  areaScanTime: string;
  areaScanQueries: string;
  areaScanCached: string;
  datalasticLiveAis: string;
  datalasticUnavailable: string;

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
  operatingStatusTitle: string;
  coverageStatus: string;
  provenance: string;
  freshnessFresh: string;
  noFreshSource: string;
  ageUnavailable: string;
  cloudCoverageNote: string;
  noCoverageNote: string;
  demoCoverageNote: string;
  provenanceCloud: string;
  provenanceEdge: string;
  provenanceReplay: string;
  provenanceNoSource: string;
  provenanceDemo: string;

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
  operatingContext: string;
  operatingContextNote: string;
  routedTotal: string;
  unmetTotal: string;
  highestPriority: string;
  supportingDetail: string;
  allocationTo: string;
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
  intelligenceTitle: "船舶情報",
  intelligenceIdentity: "身分",
  intelligenceName: "名稱",
  intelligenceType: "類型",
  intelligenceFlag: "船旗",
  intelligenceImo: "IMO",
  intelligenceBehavior: "行為摘要",
  intelligenceObservations: "本次觀測點數",
  intelligenceSessionSpan: "觀測時間跨度",
  intelligenceTypicalRoute: "慣常航線",
  intelligenceUsualArea: "慣常作業海域",
  intelligenceReviewNotes: "複審註記",
  intelligenceNoReasons: "本次尚無可供複審的證據，分析資料累積中。",
  intelligenceNoBaseline: "無歷史航線基準，無法進行航線偏離複審。",
  intelligenceHumanReview: "需人工複審",
  intelligenceReasonLoitering: "本次觀測到低速滯留",
  intelligenceReasonSpeedChange: "本次航速變化",
  intelligenceReasonCourseChange: "本次航向變化",
  intelligenceThisSession: "本次連線",
  provenanceOfficial: "官方",
  provenanceObserved: "觀測",
  provenanceDerived: "推導",
  provenanceUnknown: "未知",
  valueUnknown: "未知",
  routeDeviationTitle: "航線偏離",
  routeDeviationStatus: "偏離狀態",
  routeDeviationDetected: "偵測到航線偏離",
  routeWithinCorridor: "位於歷史航廊範圍內",
  routeDeviationDistance: "偏離距離",
  routeDeviationBaseline: "歷史基準",
  routeDeviationConfidence: "信賴度",
  routeDeviationSource: "來源",
  routeDeviationExplanation: "證據說明",
  routeDeviationUnknown: "無航線偏離證據，狀態未知。",
  confidenceHigh: "高",
  confidenceMedium: "中",
  confidenceLow: "低",
  gisContextTitle: "地理情境",
  gisDistanceToCoast: "離岸距離",
  gisNearestPort: "最近港口",
  gisDistanceToPort: "距港口距離",
  gisMaritimeArea: "所在海域",
  gisNotWithinArea: "不在任何命名區域內",
  gisOutsideCoverage: "超出參考範圍",
  historicalBaselineTitle: "歷史基準",
  historicalObservedDays: "歷史觀測天數",
  historicalObservations: "歷史觀測筆數",
  historicalTracks: "歷史軌跡數",
  historicalMovementCorridor: "歷史移動航廊",
  historicalBaselineAvailable: "歷史基準可用",
  historicalCorridorAvailable: "歷史移動航廊可用",
  historicalInsufficient: "歷史資料不足",
  historicalNotFound: "此船舶無可用的歷史基準。",
  historicalUnavailable: "歷史基準目前無法使用。",
  historicalGfwSource: "Global Fishing Watch 歷史船舶出現資料",
  satelliteEvidenceTitle: "衛星證據",
  satelliteAvailability: "可用狀態",
  satelliteProvider: "供應者",
  satelliteSceneId: "場景 ID",
  satellitePlatform: "平台",
  satelliteObservedDatetime: "觀測時間",
  satelliteOrbit: "軌道",
  demoIllustrativeLabel: "示範 / 說明用資料（非即時 AIS）",
  demoViewVessel: "檢視示範船舶",
  demoPositionStatus: "示範 / 說明用途",
  demoSourceLabel: "示範資料",
  areaScan: "區域掃描",
  areaScanPolygon: "多邊形",
  areaScanRectangle: "矩形",
  areaScanDrawHint: "在地圖上繪製掃描範圍",
  areaScanReady: "已選取區域",
  areaScanOperatorCredential: "區域掃描操作密碼",
  areaScanOperatorCredentialHint: "輸入伺服器設定的操作密碼",
  areaScanAuthenticate: "啟用區域掃描",
  areaScanAuthenticating: "驗證中…",
  areaScanAuthenticated: "區域掃描工作階段已啟用",
  areaScanAuthFailed: "區域掃描操作驗證失敗",
  areaScanSessionExpired: "區域掃描工作階段已失效，請重新驗證",
  scanArea: "掃描區域",
  clearAreaScan: "清除",
  areaScanning: "掃描中…",
  areaScanResults: "掃描船舶",
  areaScanTime: "掃描時間",
  areaScanQueries: "供應商查詢",
  areaScanCached: "快取結果",
  datalasticLiveAis: "Datalastic Live AIS",
  datalasticUnavailable: "Datalastic Live AIS 目前無法使用",
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
  operatingStatusTitle: "運作狀態",
  coverageStatus: "涵蓋範圍",
  provenance: "資料來源脈絡",
  freshnessFresh: "最新",
  noFreshSource: "無最新來源",
  ageUnavailable: "資料時間未知",
  cloudCoverageNote: "廣域網路來源；可用性取決於網路與服務連線。",
  noCoverageNote: "目前沒有最新即時來源；畫面可能保留已標示的快取或較舊資料。",
  demoCoverageNote: "明確啟用的示範資料，並非即時來源。",
  provenanceCloud: "雲端網路 AIS 來源",
  provenanceEdge: "本地無線電 AIS 接收器",
  provenanceReplay: "錄製 AIS 重播（模擬）",
  provenanceNoSource: "無最新來源；快取或較舊資料仍保留標示",
  provenanceDemo: "離線示範資料（模擬）",

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
    operatingContext: "目前運作情境",
    operatingContextNote: "僅供顯示的 Phase 8 即時來源狀態；物流決策支援不受其影響。",
    routedTotal: "已安排總量",
    unmetTotal: "未滿足總量",
    highestPriority: "最高優先配置",
    supportingDetail: "詳細依據",
    allocationTo: "配置至",
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
  intelligenceTitle: "Vessel Intelligence",
  intelligenceIdentity: "Identity",
  intelligenceName: "Name",
  intelligenceType: "Type",
  intelligenceFlag: "Flag",
  intelligenceImo: "IMO",
  intelligenceBehavior: "Behavior Summary",
  intelligenceObservations: "Observations (this session)",
  intelligenceSessionSpan: "Session span",
  intelligenceTypicalRoute: "Typical route",
  intelligenceUsualArea: "Usual operating area",
  intelligenceReviewNotes: "Review Notes",
  intelligenceNoReasons: "No evidence to review yet this session; collecting data for analysis.",
  intelligenceNoBaseline: "No historical baseline available for route-deviation review.",
  intelligenceHumanReview: "Human review required",
  intelligenceReasonLoitering: "Low-speed dwell observed this session",
  intelligenceReasonSpeedChange: "Speed changed this session",
  intelligenceReasonCourseChange: "Course changed this session",
  intelligenceThisSession: "this session",
  provenanceOfficial: "official",
  provenanceObserved: "observed",
  provenanceDerived: "derived",
  provenanceUnknown: "unknown",
  valueUnknown: "Unknown",
  routeDeviationTitle: "Route Deviation",
  routeDeviationStatus: "Status",
  routeDeviationDetected: "Route deviation detected",
  routeWithinCorridor: "Within historical corridor",
  routeDeviationDistance: "Distance",
  routeDeviationBaseline: "Baseline",
  routeDeviationConfidence: "Confidence",
  routeDeviationSource: "Source",
  routeDeviationExplanation: "Evidence",
  routeDeviationUnknown: "No route-deviation evidence; status unknown.",
  confidenceHigh: "HIGH",
  confidenceMedium: "MEDIUM",
  confidenceLow: "LOW",
  gisContextTitle: "Geographic Context",
  gisDistanceToCoast: "Distance to coast",
  gisNearestPort: "Nearest port",
  gisDistanceToPort: "Distance to port",
  gisMaritimeArea: "Within area(s)",
  gisNotWithinArea: "Not within a named area",
  gisOutsideCoverage: "Outside reference coverage",
  historicalBaselineTitle: "Historical Baseline",
  historicalObservedDays: "Observed Days",
  historicalObservations: "Historical Observations",
  historicalTracks: "Historical Tracks",
  historicalMovementCorridor: "Historical Movement Corridor",
  historicalBaselineAvailable: "Baseline Available",
  historicalCorridorAvailable: "Historical movement corridor available",
  historicalInsufficient: "Insufficient historical data",
  historicalNotFound: "Historical baseline not available for this vessel.",
  historicalUnavailable: "Historical baseline unavailable.",
  historicalGfwSource: "Global Fishing Watch historical presence",
  satelliteEvidenceTitle: "Satellite Evidence",
  satelliteAvailability: "Availability",
  satelliteProvider: "Provider",
  satelliteSceneId: "Scene ID",
  satellitePlatform: "Platform",
  satelliteObservedDatetime: "Observed datetime",
  satelliteOrbit: "Orbit",
  demoIllustrativeLabel: "DEMO / illustrative data (not live AIS)",
  demoViewVessel: "View demo vessel",
  demoPositionStatus: "DEMO / Illustrative",
  demoSourceLabel: "Demo fixture",
  areaScan: "Area Scan",
  areaScanPolygon: "Polygon",
  areaScanRectangle: "Rectangle",
  areaScanDrawHint: "Draw a scan area on the map",
  areaScanReady: "Area selected",
  areaScanOperatorCredential: "Area Scan operator credential",
  areaScanOperatorCredentialHint: "Enter the server-configured operator credential",
  areaScanAuthenticate: "Enable Area Scan",
  areaScanAuthenticating: "Authenticating…",
  areaScanAuthenticated: "Area Scan session enabled",
  areaScanAuthFailed: "Area Scan operator authentication failed",
  areaScanSessionExpired: "Area Scan session expired; authenticate again",
  scanArea: "Scan Area",
  clearAreaScan: "Clear",
  areaScanning: "Scanning…",
  areaScanResults: "Vessels found",
  areaScanTime: "Scan time",
  areaScanQueries: "Provider queries",
  areaScanCached: "Cached result",
  datalasticLiveAis: "Datalastic Live AIS",
  datalasticUnavailable: "Datalastic Live AIS currently unavailable",
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
  operatingStatusTitle: "Operating status",
  coverageStatus: "Coverage",
  provenance: "Provenance",
  freshnessFresh: "Fresh",
  noFreshSource: "No fresh source",
  ageUnavailable: "age unavailable",
  cloudCoverageNote: "Broad network feed; availability depends on Internet and service connectivity.",
  noCoverageNote: "No fresh live source; labeled cached or stale records may remain visible.",
  demoCoverageNote: "Explicit demo data, not a live source.",
  provenanceCloud: "Cloud network AIS feed",
  provenanceEdge: "Local RF AIS receiver",
  provenanceReplay: "Recorded AIS replay (simulated)",
  provenanceNoSource: "No fresh source; cached or stale records remain labeled",
  provenanceDemo: "Offline demo data (simulated)",

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
    operatingContext: "Current operating context",
    operatingContextNote:
      "Display-only Phase 8 live-source status; the logistics decision support is unaffected by it.",
    routedTotal: "Routed total",
    unmetTotal: "Unmet total",
    highestPriority: "Highest-priority allocation",
    supportingDetail: "Supporting detail",
    allocationTo: "allocated to",
  },
};

export const DICTIONARIES: Record<Lang, Dict> = {
  "zh-Hant": zhHant,
  en,
};
