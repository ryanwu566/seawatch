import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  watchApi,
  type AlertDetail,
  type AlertSummary,
  type ConfigPayload,
  type DetectionSource,
  type Evaluation,
  type RegionInfo,
  type ReviewStatus,
  type Scenario,
  type TrackDto,
  type TruthEvent,
} from "./api";
import { setDisplayTimezone } from "./lib";

export const SPEEDS = [
  { label: "1h/s", sec: 3600 },
  { label: "3h/s", sec: 10800 },
  { label: "6h/s", sec: 21600 },
];

export interface WatchState {
  ready: boolean;
  error: string | null;
  source: DetectionSource;
  scenario: Scenario | null;
  tracks: TrackDto[];
  alerts: AlertSummary[];
  dismissed: AlertSummary[];
  endAlerts: AlertSummary[];
  selectedId: string | null;
  detail: AlertDetail | null;
  config: ConfigPayload | null;
  evaluation: Evaluation | null;
  truth: TruthEvent[];
  clock: number;
  playing: boolean;
  speed: number;
  select: (id: string | null) => void;
  setClock: (t: number) => void;
  setPlaying: (p: boolean) => void;
  setSpeed: (s: number) => void;
  setStatus: (id: string, status: ReviewStatus, note?: string) => Promise<void>;
  addNote: (id: string, text: string) => Promise<void>;
  changeConfig: (values: Record<string, number>) => void;
  resetConfig: () => Promise<void>;
  resetFeedback: () => Promise<void>;
  loadTruth: () => Promise<void>;
  busy: boolean;
  regions: RegionInfo[];
  region: string;
  switchRegion: (id: string) => Promise<void>;
  switchSource: (source: DetectionSource) => void;
}

export function useWatch(): WatchState {
  const [source, setSource] = useState<DetectionSource>("scenario");
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [tracks, setTracks] = useState<TrackDto[]>([]);
  const [alerts, setAlerts] = useState<AlertSummary[]>([]);
  const [dismissed, setDismissed] = useState<AlertSummary[]>([]);
  const [endAlerts, setEndAlerts] = useState<AlertSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [truth, setTruth] = useState<TruthEvent[]>([]);
  const [clock, setClockState] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(SPEEDS[0].sec);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [regions, setRegions] = useState<RegionInfo[]>([]);
  const [region, setRegion] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const clockRef = useRef(0);
  const cfgTimer = useRef<number | undefined>(undefined);
  const fetchSeq = useRef(0);
  const detailSeq = useRef(0);
  const sourceVersionRef = useRef(0);
  const sourceVersion = sourceVersionRef.current;

  const setClock = useCallback((t: number) => {
    clockRef.current = t;
    setClockState(t);
  }, []);

  // initial load
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [sc, tr, cfg, rg] = await Promise.all([
          watchApi.scenario(source),
          watchApi.tracks(source),
          watchApi.config(),
          watchApi.regions(),
        ]);
        if (cancelled) return;
        setError(null);
        setDisplayTimezone(sc.timezone);
        setRegions(rg.regions);
        setRegion(rg.active);
        setScenario(sc);
        setTracks(tr);
        setConfig(cfg);
        setClock(sc.t1);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Cannot reach the SeaWatch detection API");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [setClock, reloadKey, source]);

  const refreshAlerts = useCallback(async (t: number, atEnd: boolean) => {
    const seq = ++fetchSeq.current;
    try {
      const [a, d] = await Promise.all([
        watchApi.alerts(source === "live" || atEnd ? undefined : t, source),
        watchApi.dismissed(source),
      ]);
      if (seq !== fetchSeq.current || sourceVersion !== sourceVersionRef.current) return;
      setAlerts(a);
      setDismissed(d);
      if (atEnd) setEndAlerts(a);
    } catch (e) {
      if (seq === fetchSeq.current && sourceVersion === sourceVersionRef.current) {
        setError(e instanceof Error ? e.message : "Alert refresh failed");
      }
    }
  }, [source, sourceVersion]);

  const refreshEvaluation = useCallback(async () => {
    if (source === "live") {
      setEvaluation(null);
      return;
    }
    try {
      const next = await watchApi.evaluation();
      if (sourceVersion === sourceVersionRef.current) setEvaluation(next);
    } catch {
      /* evaluation is optional context */
    }
  }, [source, sourceVersion]);

  // alerts follow the replay clock (throttled while playing)
  useEffect(() => {
    if (!scenario) return;
    const atEnd = clock >= scenario.t1;
    const id = window.setTimeout(() => void refreshAlerts(clock, atEnd), playing ? 0 : 120);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario, playing ? Math.floor(clock / 900) : clock, refreshAlerts]);

  useEffect(() => {
    if (scenario) void refreshEvaluation();
  }, [scenario, refreshEvaluation]);

  // playback loop
  useEffect(() => {
    if (source !== "scenario" || !playing || !scenario) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      const next = Math.min(scenario.t1, clockRef.current + dt * speed);
      setClock(next);
      if (next >= scenario.t1) {
        setPlaying(false);
        return;
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, source, speed, scenario, setClock]);

  const loadDetail = useCallback(async (id: string) => {
    const seq = ++detailSeq.current;
    try {
      const next = await watchApi.alert(id, source);
      if (seq === detailSeq.current && sourceVersion === sourceVersionRef.current) setDetail(next);
    } catch {
      if (seq === detailSeq.current && sourceVersion === sourceVersionRef.current) setDetail(null);
    }
  }, [source, sourceVersion]);

  const select = useCallback(
    (id: string | null) => {
      setSelectedId(id);
      if (!id) {
        detailSeq.current += 1;
        setDetail(null);
      }
      else void loadDetail(id);
    },
    [loadDetail],
  );

  const after = useCallback(async () => {
    await Promise.all([refreshAlerts(clockRef.current, scenario ? clockRef.current >= scenario.t1 : true), refreshEvaluation()]);
  }, [refreshAlerts, refreshEvaluation, scenario]);

  const setStatus = useCallback(
    async (id: string, status: ReviewStatus, note?: string) => {
      setBusy(true);
      try {
        const next = await watchApi.setStatus(id, status, note, source);
        if (sourceVersion !== sourceVersionRef.current) return;
        setDetail(next);
        await after();
      } finally {
        setBusy(false);
      }
    },
    [after, source, sourceVersion],
  );

  const addNote = useCallback(
    async (id: string, text: string) => {
      const next = await watchApi.addNote(id, text, source);
      if (sourceVersion !== sourceVersionRef.current) return;
      setDetail(next);
      await after();
    },
    [after, source, sourceVersion],
  );

  const changeConfig = useCallback(
    (values: Record<string, number>) => {
      if (source !== "scenario") return;
      setConfig((c) => (c ? { ...c, values: { ...c.values, ...values } } : c));
      window.clearTimeout(cfgTimer.current);
      cfgTimer.current = window.setTimeout(async () => {
        setBusy(true);
        try {
          const cfg = await watchApi.setConfig(values);
          if (sourceVersion !== sourceVersionRef.current) return;
          setConfig(cfg);
          await after();
          if (selectedId) await loadDetail(selectedId);
        } finally {
          setBusy(false);
        }
      }, 350);
    },
    [after, loadDetail, selectedId, source, sourceVersion],
  );

  const resetConfig = useCallback(async () => {
    if (source !== "scenario") return;
    const next = await watchApi.resetConfig();
    if (sourceVersion !== sourceVersionRef.current) return;
    setConfig(next);
    await after();
  }, [after, source, sourceVersion]);

  const resetFeedback = useCallback(async () => {
    if (source !== "scenario") return;
    await watchApi.resetFeedback();
    if (sourceVersion !== sourceVersionRef.current) return;
    await after();
    if (selectedId) await loadDetail(selectedId);
  }, [after, loadDetail, selectedId, source, sourceVersion]);

  const switchRegion = useCallback(async (id: string) => {
    if (source !== "scenario") return;
    setBusy(true);
    try {
      await watchApi.selectRegion(id);
      if (sourceVersion !== sourceVersionRef.current) return;
      setScenario(null);
      setTracks([]);
      setAlerts([]);
      setDismissed([]);
      setEndAlerts([]);
      detailSeq.current += 1;
      setSelectedId(null);
      setDetail(null);
      setEvaluation(null);
      setTruth([]);
      setPlaying(false);
      setReloadKey((k) => k + 1);
    } finally {
      setBusy(false);
    }
  }, [source, sourceVersion]);

  const loadTruth = useCallback(async () => {
    if (source !== "scenario") return;
    const next = await watchApi.truth();
    if (sourceVersion === sourceVersionRef.current) setTruth(next);
  }, [source, sourceVersion]);

  const switchSource = useCallback((next: DetectionSource) => {
    if (next === source) return;
    sourceVersionRef.current += 1;
    fetchSeq.current += 1;
    detailSeq.current += 1;
    window.clearTimeout(cfgTimer.current);
    setSource(next);
    setScenario(null);
    setTracks([]);
    setAlerts([]);
    setDismissed([]);
    setEndAlerts([]);
    setSelectedId(null);
    setDetail(null);
    setEvaluation(null);
    setTruth([]);
    setPlaying(false);
    setError(null);
  }, [source]);

  return useMemo(
    () => ({
      ready: !!scenario && !!config, error, source, scenario, tracks, alerts, dismissed, endAlerts, selectedId, detail, config, evaluation, truth,
      clock, playing, speed, select, setClock, setPlaying, setSpeed, setStatus, addNote, changeConfig, resetConfig,
      resetFeedback, loadTruth, busy, regions, region, switchRegion, switchSource,
    }),
    [scenario, config, error, source, tracks, alerts, dismissed, endAlerts, selectedId, detail, evaluation, truth, clock, playing, speed, select,
      setClock, setStatus, addNote, changeConfig, resetConfig, resetFeedback, loadTruth, busy, regions, region, switchRegion, switchSource],
  );
}
