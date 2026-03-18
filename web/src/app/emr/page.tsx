"use client";

export const dynamic = "force-dynamic";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import mammoth from "mammoth";
import { flashSuccessButton } from "../lib/flash";

type EmrResponse = Record<string, unknown> | Array<Record<string, unknown>>;
type ReportPayload = Record<string, unknown> | null;
type ReportFile = {
  date: string;
  name: string;
  size_bytes: number;
  url: string;
  updated_at: number;
};
type PatientSearchResult = {
  patient_id: string;
  name?: string | null;
  gender?: string | null;
  age?: number | null;
  phone?: string | null;
  id_card?: string | null;
};

type RoiOverlayPoint = {
  name: string;
  meanC: number;
  x: number;
  y: number;
};

type RoiOverlayLayoutPoint = RoiOverlayPoint & {
  labelX: number;
  labelY: number;
  showLeader: boolean;
};

const ROI_LABEL_POSITIONS: Record<string, { x: number; y: number }> = {
  "额头": { x: 50, y: 9 },
  "左眼": { x: 45, y: 13 },
  "右眼": { x: 55, y: 13 },
  "鼻子": { x: 50, y: 16 },
  "左脸颊": { x: 42, y: 18 },
  "右脸颊": { x: 58, y: 18 },
  "下巴": { x: 50, y: 22 },
  "颈部": { x: 50, y: 28 },
  "胸部": { x: 50, y: 38 },
  "腹部": { x: 50, y: 52 },
  "左臂": { x: 30, y: 40 },
  "右臂": { x: 70, y: 40 },
  "左腿": { x: 44, y: 74 },
  "右腿": { x: 56, y: 74 },
};

const THERMAL_PLOT_BOUNDS = {
  left: 3,
  right: 72,
  top: 8,
  bottom: 97,
};

const HEAD_ROI_NAME_REGEX = /(额头|眼|脸颊|鼻子|鼻|下巴)/;

const API_BASE = "http://localhost:8000";
const EMR_STATE_KEY = "patient_flow_state_emr";
const REPORTS_PAGE_SIZE = 10;

function EmrPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [recordId, setRecordId] = useState("");
  const [emrId, setEmrId] = useState("");
  const [patientId, setPatientId] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [doctorOpinion, setDoctorOpinion] = useState("");
  const [archived, setArchived] = useState(false);
  const [report, setReport] = useState<ReportPayload>(null);
  const [reportFiles, setReportFiles] = useState<ReportFile[]>([]);
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [showPreview, setShowPreview] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const [output, setOutput] = useState<EmrResponse | { error: string }>({
    error: "请先执行操作",
  });
  const [showAllReports, setShowAllReports] = useState(false);
  const [globalQuery, setGlobalQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<PatientSearchResult[]>([]);
  const [searchMessage, setSearchMessage] = useState("");
  const [currentSearchPatient, setCurrentSearchPatient] = useState<PatientSearchResult | null>(null);
  const [showAbnormalDetails, setShowAbnormalDetails] = useState(false);
  const [reportPage, setReportPage] = useState(1);
  const [incomingEmrToast, setIncomingEmrToast] = useState<{
    emrId: string;
    patientId: string;
    message: string;
  } | null>(null);
  const [ingestProgress, setIngestProgress] = useState(0);
  const [ingestStep, setIngestStep] = useState(0);
  const [ingestStatus, setIngestStatus] = useState("");
  const [ingestRunning, setIngestRunning] = useState(false);
  const latestKnownEmrIdRef = useRef("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(EMR_STATE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as Record<string, string>;
      if (data.recordId) setRecordId(data.recordId);
      if (data.emrId) setEmrId(data.emrId);
      if (data.patientId) setPatientId(data.patientId);
      if (data.diagnosis) setDiagnosis(data.diagnosis);
      if (data.doctorOpinion) setDoctorOpinion(data.doctorOpinion);
      if (typeof data.archived === "string") {
        setArchived(data.archived === "true");
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    if (globalQuery.trim()) return;
    try {
      const rawPatients = localStorage.getItem("patient_flow_state_patients");
      const rawLastEmr = localStorage.getItem("last_emr_context");
      const patientsState = rawPatients
        ? (JSON.parse(rawPatients) as Record<string, unknown>)
        : null;
      const lastEmrContext = rawLastEmr
        ? (JSON.parse(rawLastEmr) as Record<string, unknown>)
        : null;
      const currentPatient = patientsState && typeof patientsState === "object"
        ? (patientsState as Record<string, unknown>).currentPatient
        : null;
      const candidate = (currentPatient && typeof currentPatient === "object")
        ? (currentPatient as Record<string, unknown>)
        : (lastEmrContext && typeof lastEmrContext === "object")
          ? lastEmrContext as Record<string, unknown>
          : null;

      if (!candidate) return;

      const candidateName = String(candidate.name ?? "").trim();
      const candidateId = String(candidate.patient_id ?? "").trim();
      if (candidateName || candidateId) {
        setGlobalQuery(candidateName || candidateId);
      }
      if (!patientId && candidateId) {
        setPatientId(candidateId);
      }
      if (!currentSearchPatient && (candidateName || candidateId)) {
        setCurrentSearchPatient({
          patient_id: candidateId,
          name: candidateName || null,
          gender: typeof candidate.gender === "string" ? candidate.gender : null,
          age: typeof candidate.age === "number" ? candidate.age : null,
        });
      }
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        EMR_STATE_KEY,
        JSON.stringify({
          recordId,
          emrId,
          patientId,
          diagnosis,
          doctorOpinion,
          archived: String(archived),
        })
      );
    } catch {
      // ignore storage errors
    }
  }, [recordId, emrId, patientId, diagnosis, doctorOpinion, archived]);

  useEffect(() => {
    if (!report || typeof report !== "object") {
      return;
    }
    const patient = (report as Record<string, unknown>).patient as Record<string, unknown> | undefined;
    if (!patient) {
      return;
    }
    const context = {
      emr_id: emrId || "",
      patient_id: String(patient.patient_id || ""),
      name: String(patient.name || ""),
      gender: String(patient.gender || ""),
      age: patient.age !== undefined && patient.age !== null ? Number(patient.age) : undefined,
    };
    try {
      localStorage.setItem("last_emr_context", JSON.stringify(context));
    } catch {
      // ignore storage errors
    }
  }, [report, emrId]);

  const outputText = useMemo(() => JSON.stringify(output, null, 2), [output]);
  const currentPatientName = useMemo(() => {
    if (report && typeof report.patient === "object") {
      const patient = report.patient as Record<string, unknown>;
      return String(patient.name || "").trim();
    }
    if (currentSearchPatient?.name) {
      return String(currentSearchPatient.name || "").trim();
    }
    return "";
  }, [currentSearchPatient, report]);
  const currentPatientIdForFilter = useMemo(() => {
    if (report && typeof report.patient === "object") {
      const patient = report.patient as Record<string, unknown>;
      const idValue = String(patient.patient_id || "").trim();
      return idValue || patientId.trim();
    }
    if (currentSearchPatient?.patient_id) {
      return String(currentSearchPatient.patient_id || "").trim();
    }
    return patientId.trim();
  }, [currentSearchPatient, patientId, report]);
  const visibleReportFiles = useMemo(() => {
    if (reportFiles.length === 0) {
      return [] as ReportFile[];
    }
    if (showAllReports) {
      return reportFiles;
    }
    const normalizedName = currentPatientName.trim();
    const normalizedId = currentPatientIdForFilter.trim();
    if (!normalizedName && !normalizedId) {
      return reportFiles;
    }
    const prefix = normalizedName ? `${normalizedName}_` : "";
    const nameKey = normalizedName.toLowerCase();
    const idKey = normalizedId.toLowerCase();
    return reportFiles.filter((file) => {
      const fileName = file.name.toLowerCase();
      const matchName =
        !!normalizedName && (file.name.startsWith(prefix) || fileName.includes(nameKey));
      const matchId = !!normalizedId && fileName.includes(idKey);
      return matchName || matchId;
    });
  }, [currentPatientIdForFilter, currentPatientName, reportFiles, showAllReports]);

  const reportFilesForDisplay = useMemo(() => {
    return visibleReportFiles.length ? visibleReportFiles : reportFiles;
  }, [reportFiles, visibleReportFiles]);

  const reportTotalPages = useMemo(() => {
    if (!reportFilesForDisplay.length) {
      return 1;
    }
    return Math.max(1, Math.ceil(reportFilesForDisplay.length / REPORTS_PAGE_SIZE));
  }, [reportFilesForDisplay]);

  const paginatedReportFiles = useMemo(() => {
    const start = (reportPage - 1) * REPORTS_PAGE_SIZE;
    const end = start + REPORTS_PAGE_SIZE;
    return reportFilesForDisplay.slice(start, end);
  }, [reportFilesForDisplay, reportPage]);

  useEffect(() => {
    setReportPage(1);
  }, [showAllReports, currentPatientName, currentPatientIdForFilter]);

  useEffect(() => {
    if (reportPage > reportTotalPages) {
      setReportPage(reportTotalPages);
    }
  }, [reportPage, reportTotalPages]);

  const overview = useMemo(() => {
    const analysis = report && typeof report.analysis === "object"
      ? (report.analysis as Record<string, unknown>)
      : undefined;
    const metrics = analysis?.temperature_metrics && typeof analysis.temperature_metrics === "object"
      ? (analysis.temperature_metrics as Record<string, unknown>)
      : undefined;
    const abnormalRegions = analysis?.regional_comparison &&
      typeof analysis.regional_comparison === "object" &&
      (analysis.regional_comparison as Record<string, unknown>).abnormal_regions &&
      Array.isArray((analysis.regional_comparison as Record<string, unknown>).abnormal_regions)
      ? ((analysis.regional_comparison as Record<string, unknown>).abnormal_regions as unknown[])
      : [];

    const minC = toNumber(metrics?.min_c);
    const maxC = toNumber(metrics?.max_c);
    const tempRange =
      minC !== null && maxC !== null
        ? `${(maxC - minC).toFixed(1)}°C`
        : "-";

    const latestReport = reportFiles.length
      ? reportFiles.reduce((latest, file) =>
          file.updated_at > latest.updated_at ? file : latest
        )
      : undefined;

    return {
      riskLevel: String(analysis?.risk_level ?? "-").toUpperCase(),
      abnormalCount: abnormalRegions.length,
      tempRange,
      reportCount: showAllReports ? reportFiles.length : visibleReportFiles.length,
      latestReportLabel: latestReport?.date || latestReport?.name || "-",
    };
  }, [report, reportFiles, showAllReports, visibleReportFiles.length]);

  const abnormalRegionList = useMemo(() => {
    const analysis = report && typeof report.analysis === "object"
      ? (report.analysis as Record<string, unknown>)
      : undefined;
    const comparison = analysis?.regional_comparison && typeof analysis.regional_comparison === "object"
      ? (analysis.regional_comparison as Record<string, unknown>)
      : undefined;
    const regions = comparison?.abnormal_regions;
    if (!Array.isArray(regions)) {
      return [] as Record<string, unknown>[];
    }
    return regions as Record<string, unknown>[];
  }, [report]);

  const roiOverlayPoints = useMemo(() => {
    if (!report || typeof report !== "object") {
      return [] as RoiOverlayPoint[];
    }
    const analysis = report.analysis && typeof report.analysis === "object"
      ? (report.analysis as Record<string, unknown>)
      : undefined;
    const roiAnalysis = analysis?.roi_analysis && typeof analysis.roi_analysis === "object"
      ? (analysis.roi_analysis as Record<string, unknown>)
      : undefined;
    const roiList = roiAnalysis?.roi_list;
    if (!Array.isArray(roiList)) {
      return [] as RoiOverlayPoint[];
    }

    const points: RoiOverlayPoint[] = [];
    for (const item of roiList as Record<string, unknown>[]) {
      const rawName = String(item.name || "").trim();
      if (!rawName) {
        continue;
      }
      const normalizedName = rawName.replace(/_/g, " ");
      const mappedName = ROI_LABEL_POSITIONS[rawName] ? rawName : normalizedName;
      const meanC = toNumber(item.mean_c);
      if (meanC === null) {
        continue;
      }

      let pos = ROI_LABEL_POSITIONS[mappedName] || ROI_LABEL_POSITIONS[rawName];
      const centerXPct = toNumber(item.center_x_pct);
      const centerYPct = toNumber(item.center_y_pct);
      if (centerXPct !== null && centerYPct !== null) {
        const clampedX = Math.max(0, Math.min(100, centerXPct));
        const clampedY = Math.max(0, Math.min(100, centerYPct));
        pos = {
          x:
            THERMAL_PLOT_BOUNDS.left
            + (clampedX / 100) * (THERMAL_PLOT_BOUNDS.right - THERMAL_PLOT_BOUNDS.left),
          y:
            THERMAL_PLOT_BOUNDS.top
            + (clampedY / 100) * (THERMAL_PLOT_BOUNDS.bottom - THERMAL_PLOT_BOUNDS.top),
        };
      }

      if (!pos) {
        continue;
      }
      points.push({
        name: mappedName,
        meanC,
        x: pos.x,
        y: pos.y,
      });
    }

    return points.sort((a, b) => b.meanC - a.meanC);
  }, [report]);

  const roiOverlayLayoutPoints = useMemo(() => {
    if (roiOverlayPoints.length === 0) {
      return [] as RoiOverlayLayoutPoint[];
    }

    const clampPercent = (value: number, min: number, max: number) =>
      Math.max(min, Math.min(max, value));

    const labelBoxWidthPct = 12;
    const labelBoxHeightPct = 4.8;
    const minVerticalGapPct = 5.2;
    const minHorizontalGapPct = 8.0;
    const plotCenterX = (THERMAL_PLOT_BOUNDS.left + THERMAL_PLOT_BOUNDS.right) / 2;
    const headLeftLaneX = plotCenterX - 8.5;
    const headRightLaneX = plotCenterX + 8.5;
    const headTopMinY = THERMAL_PLOT_BOUNDS.top + 2;
    const headBottomMaxY = THERMAL_PLOT_BOUNDS.top + 25;

    const placed: RoiOverlayLayoutPoint[] = [];

    const ensureNoOverlap = (
      candidateX: number,
      candidateY: number,
      minY: number,
      maxY: number
    ) => {
      let x = candidateX;
      let y = candidateY;
      for (let tries = 0; tries < 14; tries += 1) {
        const overlap = placed.find((item) => {
          const horizontalHit =
            Math.abs(item.labelX - x) < minHorizontalGapPct;
          const verticalHit =
            Math.abs(item.labelY - y) < minVerticalGapPct;
          return horizontalHit && verticalHit;
        });
        if (!overlap) {
          return {
            x: clampPercent(x, 3, 97),
            y: clampPercent(y, minY, maxY),
          };
        }
        y = overlap.labelY + minVerticalGapPct;
        if (y > maxY) {
          y = overlap.labelY - minVerticalGapPct;
          x += x <= plotCenterX ? -3 : 3;
        }
      }

      return {
        x: clampPercent(x, 3, 97),
        y: clampPercent(y, minY, maxY),
      };
    };

    const headPoints = roiOverlayPoints
      .filter((point) => HEAD_ROI_NAME_REGEX.test(point.name) || point.y <= 33)
      .sort((a, b) => a.y - b.y || a.x - b.x);

    let leftLaneNextY = headTopMinY;
    let rightLaneNextY = headTopMinY;
    let centerAlternator = false;

    for (const point of headPoints) {
      let laneX = point.x <= plotCenterX ? headLeftLaneX : headRightLaneX;
      if (Math.abs(point.x - plotCenterX) < 2.8) {
        laneX = centerAlternator ? headRightLaneX : headLeftLaneX;
        centerAlternator = !centerAlternator;
      }

      const preferredY = clampPercent(point.y, headTopMinY, headBottomMaxY);
      const laneNextY = laneX < plotCenterX ? leftLaneNextY : rightLaneNextY;
      const seedY = Math.max(preferredY, laneNextY);
      const safe = ensureNoOverlap(laneX, seedY, headTopMinY, headBottomMaxY);

      placed.push({
        ...point,
        labelX: safe.x,
        labelY: safe.y,
        showLeader: true,
      });

      if (laneX < plotCenterX) {
        leftLaneNextY = safe.y + minVerticalGapPct;
      } else {
        rightLaneNextY = safe.y + minVerticalGapPct;
      }
    }

    const bodyPoints = roiOverlayPoints.filter((point) =>
      !headPoints.some((head) => head.name === point.name && head.x === point.x && head.y === point.y)
    );

    for (const point of bodyPoints) {
      const minY = THERMAL_PLOT_BOUNDS.top;
      const maxY = THERMAL_PLOT_BOUNDS.bottom;
      const safe = ensureNoOverlap(point.x, point.y, minY, maxY);
      const moved =
        Math.abs(safe.x - point.x) > labelBoxWidthPct / 3 ||
        Math.abs(safe.y - point.y) > labelBoxHeightPct / 3;

      placed.push({
        ...point,
        labelX: safe.x,
        labelY: safe.y,
        showLeader: moved,
      });
    }

    return placed;
  }, [roiOverlayPoints]);

  const patientSummary = useMemo(() => {
    if (report && typeof report.patient === "object") {
      const patient = report.patient as Record<string, unknown>;
      return {
        name: String(patient.name || "-").trim() || "-",
        gender: formatGender(String(patient.gender || "-")),
        age: patient.age !== undefined && patient.age !== null ? String(patient.age) : "-",
        bodyPart: String(patient.body_part || "-").trim() || "-",
      };
    }
    if (currentSearchPatient) {
      return {
        name: String(currentSearchPatient.name || "-").trim() || "-",
        gender: formatGender(String(currentSearchPatient.gender || "-")),
        age:
          currentSearchPatient.age !== undefined && currentSearchPatient.age !== null
            ? String(currentSearchPatient.age)
            : "-",
        bodyPart: "-",
      };
    }
    return {
      name: "-",
      gender: "-",
      age: "-",
      bodyPart: "-",
    };
  }, [currentSearchPatient, report]);

  const normalizeImagePath = useCallback((value: unknown): string => {
    const raw = String(value || "").trim();
    if (!raw) return "";
    if (/^https?:\/\//i.test(raw)) return raw;
    const stripped = raw.replace(/^\/+/, "").replace(/^data\//i, "");
    return `${API_BASE}/data/${stripped}`;
  }, []);

  // Primary marked image (with ROI overlay SVG rendered on top in browser)
  const thermalImageUrl = useMemo(() => {
    if (!report || typeof report !== "object") return "";
    const direct = normalizeImagePath(report.thermal_marked_image);
    if (direct) return direct;
    if (Array.isArray(report.thermal_images)) {
      for (const item of report.thermal_images) {
        if (String(item || "").includes("thermal_roi_labeled")) continue;
        const candidate = normalizeImagePath(item);
        if (candidate) return candidate;
      }
    }
    return "";
  }, [report, normalizeImagePath]);

  // All uploaded source images (exclude the backend-generated heatmaps)
  const uploadedThermalImageUrls = useMemo((): string[] => {
    if (!report || typeof report !== "object") return [];
    const generated = new Set(["thermal_marked.png", "thermal_roi_labeled.png"]);
    const urls: string[] = [];
    if (Array.isArray(report.thermal_images)) {
      for (const item of report.thermal_images) {
        const raw = String(item || "").trim();
        if (!raw) continue;
        const filename = raw.split("/").pop() || "";
        if (generated.has(filename)) continue;
        const url = normalizeImagePath(raw);
        if (url) urls.push(url);
      }
    }
    return urls;
  }, [report, normalizeImagePath]);

  const fetchReports = useCallback(async (silent = false) => {
    try {
      const response = await fetch(`${API_BASE}/reports`);
      const data = (await response.json()) as ReportFile[];
      setReportFiles(Array.isArray(data) ? data : []);
    } catch {
      if (!silent) {
        setReportFiles([]);
      }
    }
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      fetchReports(true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [fetchReports]);

  useEffect(() => {
    if (emrId.trim()) {
      latestKnownEmrIdRef.current = emrId.trim();
    }
  }, [emrId]);

  useEffect(() => {
    const recordIdParam = searchParams.get("record_id") || "";
    if (recordIdParam) {
      setRecordId(recordIdParam);
    }
    const patientIdParam = searchParams.get("patient_id") || "";
    if (patientIdParam) {
      setPatientId(patientIdParam);
    }
  }, [searchParams]);

  useEffect(() => {
    const rid = recordId.trim();
    if (!rid) {
      setIngestRunning(false);
      return;
    }

    let isClosed = false;
    let settleTimer: number | null = null;
    const source = new EventSource(`${API_BASE}/events/ingest-progress/${encodeURIComponent(rid)}`);

    setIngestRunning(true);
    setIngestStatus("等待后端分析进度...");

    const finishAndClose = () => {
      if (isClosed) return;
      isClosed = true;
      source.close();
      setIngestRunning(false);
    };

    source.addEventListener("progress", (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as {
          step?: number;
          label?: string;
          pct?: number;
          status?: string;
        };

        const pct = Number(payload.pct ?? 0);
        setIngestProgress(Number.isFinite(pct) ? Math.max(0, Math.min(100, pct)) : 0);
        setIngestStep(Number(payload.step ?? 0));
        setIngestStatus(String(payload.label || "分析中..."));

        if (payload.status === "complete" || pct >= 100) {
          setIngestProgress(100);
          setIngestStatus("分析完成");
          if (settleTimer) {
            window.clearTimeout(settleTimer);
          }
          settleTimer = window.setTimeout(() => {
            finishAndClose();
          }, 1200);
        }
      } catch {
        // ignore malformed event payloads
      }
    });

    source.onerror = () => {
      if (settleTimer) {
        window.clearTimeout(settleTimer);
      }
      finishAndClose();
    };

    return () => {
      if (settleTimer) {
        window.clearTimeout(settleTimer);
      }
      finishAndClose();
    };
  }, [recordId]);

  // 当URL中有record_id时，始终确保当前报告与该record_id一致
  useEffect(() => {
    const recordIdParam = searchParams.get("record_id") || "";
    if (!recordIdParam) {
      return;
    }
    if (recordId !== recordIdParam) {
      return;
    }

    const currentReportRecordId =
      report && typeof report === "object"
        ? String(report.record_id || "")
        : "";

    if (currentReportRecordId === recordIdParam) {
      return;
    }

    generateEmrByRecordId(recordIdParam);
  }, [searchParams, recordId, report]);

  useEffect(() => {
    if (!globalQuery.trim()) {
      setSearchResults([]);
      setSearchMessage("");
    }
  }, [globalQuery]);

  function extractReport(data: EmrResponse): ReportPayload {
    if (Array.isArray(data)) {
      return null;
    }
    const emr = data as Record<string, unknown>;
    if (emr.report && typeof emr.report === "object") {
      return emr.report as Record<string, unknown>;
    }
    return null;
  }

  function persistContextFromEmr(data: EmrResponse): boolean {
    if (Array.isArray(data)) {
      return false;
    }
    const emr = data as Record<string, unknown>;
    const report = emr.report as Record<string, unknown> | undefined;
    const patient = report?.patient as Record<string, unknown> | undefined;
    const resolvedEmrId = String(emr.emr_id ?? emrId ?? "");
    const resolvedPatientId = String(
      patient?.patient_id ?? emr.patient_id ?? (emr as Record<string, unknown>).patientId ?? ""
    );
    if (!resolvedEmrId) {
      return false;
    }
    const context = {
      emr_id: resolvedEmrId,
      patient_id: resolvedPatientId,
      name: String(patient?.name ?? emr.patient_name ?? emr.name ?? ""),
      gender: String(patient?.gender ?? emr.gender ?? ""),
      age:
        patient?.age !== undefined && patient?.age !== null
          ? Number(patient.age)
          : emr.age !== undefined && emr.age !== null
            ? Number(emr.age)
            : undefined,
    };
    try {
      localStorage.setItem("last_emr_context", JSON.stringify(context));
      localStorage.setItem(
        "patient_flow_state_patients",
        JSON.stringify({
          currentPatientId: context.patient_id,
          currentPatient: {
            patient_id: context.patient_id,
            name: context.name,
            gender: context.gender,
            age: context.age ?? null,
          },
        })
      );
    } catch {
      // ignore storage errors
    }
    return true;
  }

  function formatTemperatureMetricLabel(key: string) {
    const normalized = key.replace(/\s+/g, "_").toLowerCase();
    const mapping: Record<string, string> = {
      min_c: "最低温度",
      max_c: "最高温度",
      avg_c: "平均温度",
      body_avg_temp_c: "身体平均温度",
      temperature_range: "温度范围",
      count: "样本数量",
    };
    return mapping[normalized] || key;
  }

  function formatRegionLabel(value: unknown) {
    const key = String(value || "").trim().toLowerCase();
    if (!key) return "-";
    const mapping: Record<string, string> = {
      r1_c1: "左肩",
      r1_c2: "颈部",
      r1_c3: "右肩",
      r2_c1: "左背",
      r2_c2: "脊柱",
      r2_c3: "右背",
      r3_c1: "左腰",
      r3_c2: "腰部",
      r3_c3: "右腰",
      r4_c1: "左髋",
      r4_c2: "骨盆",
      r4_c3: "右髋",
      r5_c1: "左膝",
      r5_c2: "膝部",
      r5_c3: "右膝",
    };
    return mapping[key] || String(value);
  }

  function formatRoiLabel(value: unknown) {
    const raw = String(value || "").trim();
    if (!raw) return "-";
    const mapped = formatRegionLabel(raw);
    if (mapped !== raw) return mapped;
    return raw.replace(/_/g, " ");
  }

  function formatGender(value?: string) {
    if (!value) return "-";
    const normalized = String(value).toLowerCase();
    if (normalized === "male" || normalized === "m" || value === "男") return "男";
    if (normalized === "female" || normalized === "f" || value === "女") return "女";
    return String(value);
  }

  function toNumber(value: unknown): number | null {
    if (value === null || value === undefined) return null;
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  }

  function syncEmrFields(data: EmrResponse) {
    if (Array.isArray(data)) {
      return;
    }
    const emr = data as Record<string, unknown>;
    if (!emr.emr_id) {
      return;
    }
    setEmrId(String(emr.emr_id));
    setDiagnosis(String(emr.diagnosis ?? ""));
    setDoctorOpinion(String(emr.doctor_opinion ?? ""));
    setArchived(Boolean(emr.archived));
  }

  async function postJson<T>(url: string, payload: Record<string, unknown>): Promise<T> {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }

  async function putJson<T>(url: string, payload: Record<string, unknown>): Promise<T> {
    const response = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return response.json();
  }

  function resolveLatestEmrId(data: EmrResponse): string | null {
    if (!Array.isArray(data) || data.length === 0) return null;
    let latestItem: Record<string, unknown> | null = null;
    let latestTimestamp = Number.NEGATIVE_INFINITY;

    data.forEach((item) => {
      const createdAt = typeof item.created_at === "string"
        ? Date.parse(item.created_at)
        : Number.NaN;
      if (!Number.isNaN(createdAt) && createdAt >= latestTimestamp) {
        latestTimestamp = createdAt;
        latestItem = item;
      }
    });

    if (!latestItem) {
      latestItem = data[data.length - 1] as Record<string, unknown>;
    }
    const emrIdValue = latestItem?.emr_id ?? latestItem?.emrId;
    return emrIdValue ? String(emrIdValue) : null;
  }

  async function generateEmrByRecordId(nextRecordId: string) {
    const data = await postJson(`${API_BASE}/emr/generate`, {
      record_id: nextRecordId.trim(),
    });
    setOutput(data as EmrResponse);
    syncEmrFields(data as EmrResponse);
    setReport(extractReport(data as EmrResponse));
    fetchReports();
    flashSuccessButton();
    persistContextFromEmr(data as EmrResponse);
    setRedirecting(false);
  }

  async function fetchEmrById(nextEmrId: string) {
    const response = await fetch(`${API_BASE}/emr/${nextEmrId.trim()}`);
    const data = (await response.json()) as EmrResponse;
    setOutput(data);
    syncEmrFields(data);
    setReport(extractReport(data));
    if (response.ok) {
      flashSuccessButton();
    }
  }

  async function listEmrsByPatientId(nextPatientId: string): Promise<EmrResponse> {
    const query = nextPatientId.trim()
      ? `?patient_id=${encodeURIComponent(nextPatientId.trim())}`
      : "";
    const response = await fetch(`${API_BASE}/emr${query}`);
    const data = (await response.json()) as EmrResponse;
    setOutput(data);
    setReport(extractReport(data));
    if (response.ok) {
      flashSuccessButton();
    }
    return data;
  }

  async function fetchLatestEmrForPatient(nextPatientId: string) {
    const data = await listEmrsByPatientId(nextPatientId);
    const latestEmrId = resolveLatestEmrId(data);
    if (!latestEmrId) {
      setSearchMessage("未找到该患者的病历记录");
      return false;
    }
    setEmrId(latestEmrId);
    await fetchEmrById(latestEmrId);
    return true;
  }

  async function jumpToIncomingEmr() {
    if (!incomingEmrToast?.emrId) {
      return;
    }
    const targetEmrId = incomingEmrToast.emrId;
    const targetPatientId = incomingEmrToast.patientId;
    setIncomingEmrToast(null);
    if (targetPatientId) {
      setPatientId(targetPatientId);
    }
    setEmrId(targetEmrId);
    setSearchMessage("已跳转到新生成病历");
    await fetchEmrById(targetEmrId);
  }

  useEffect(() => {
    const targetPatientId = currentPatientIdForFilter.trim();
    let cancelled = false;

    const pollLatestPatientEmr = async () => {
      try {
        const query = targetPatientId
          ? `?patient_id=${encodeURIComponent(targetPatientId)}&include_archived=true&limit=20`
          : `?include_archived=true&limit=20`;
        const response = await fetch(`${API_BASE}/emr${query}`);
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as EmrResponse;
        const latestEmrId = resolveLatestEmrId(data);
        if (!latestEmrId || cancelled) {
          return;
        }

        if (!latestKnownEmrIdRef.current) {
          latestKnownEmrIdRef.current = latestEmrId;
          return;
        }

        if (latestEmrId !== latestKnownEmrIdRef.current) {
          latestKnownEmrIdRef.current = latestEmrId;
          let resolvedPatientId = targetPatientId;
          if (!resolvedPatientId && Array.isArray(data) && data.length > 0) {
            const latest = data[0] as Record<string, unknown>;
            resolvedPatientId = String(latest.patient_id || "").trim();
          }
          setIncomingEmrToast({
            emrId: latestEmrId,
            patientId: resolvedPatientId,
            message: "检测到新生成的诊断报告",
          });
          fetchReports(true);
        }
      } catch {
        // Ignore polling errors and retry on next interval.
      }
    };

    pollLatestPatientEmr();
    const timer = window.setInterval(pollLatestPatientEmr, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [currentPatientIdForFilter, fetchReports]);

  // WebSocket connection for real-time EMR notifications
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: NodeJS.Timeout | null = null;

    const connectWebSocket = () => {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/ws/notifications`;

      try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
          console.log("WebSocket connected");
        };

        ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as Record<string, unknown>;
            const msgType = String(message.type || "").trim();

            if (msgType === "emr_generated") {
              const emrId = String(message.emr_id || "").trim();
              const patientIdFromNotif = String(message.patient_id || "").trim();
              const recordId = String(message.record_id || "").trim();

              // Show toast notification
              setIncomingEmrToast({
                emrId,
                patientId: patientIdFromNotif,
                message: message.message ? String(message.message) : "诊断分析报告已生成",
              });

              // Update latest EMR tracking
              if (emrId) {
                latestKnownEmrIdRef.current = emrId;
              }

              // Refresh EMR list
              fetchReports(true);
            }
          } catch (error) {
            console.error("Failed to parse WebSocket message:", error);
          }
        };

        ws.onerror = (error) => {
          console.error("WebSocket error:", error);
        };

        ws.onclose = () => {
          console.log("WebSocket disconnected");
          // Attempt to reconnect after 5 seconds
          reconnectTimeout = setTimeout(connectWebSocket, 5000);
        };
      } catch (error) {
        console.error("Failed to create WebSocket:", error);
        // Attempt to reconnect after 5 seconds
        reconnectTimeout = setTimeout(connectWebSocket, 5000);
      }
    };

    connectWebSocket();

    return () => {
      if (ws) {
        ws.close();
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
    };
  }, [fetchReports]);

  async function handleGenerate() {
    if (!recordId.trim()) {
      setOutput({ error: "record_id 不能为空" });
      return;
    }
    setCurrentSearchPatient(null);
    await generateEmrByRecordId(recordId.trim());
  }

  async function handleFetch() {
    if (!emrId.trim()) {
      setOutput({ error: "emr_id 不能为空" });
      return;
    }
    setCurrentSearchPatient(null);
    await fetchEmrById(emrId.trim());
  }

  async function handleFetchLatestForPatient() {
    const targetPatientId = currentPatientIdForFilter.trim() || patientId.trim();
    if (!targetPatientId) {
      setSearchMessage("请先选择患者或输入患者ID");
      return;
    }
    setCurrentSearchPatient(null);
    const ok = await fetchLatestEmrForPatient(targetPatientId);
    setSearchMessage(ok ? "已读取患者最近病例" : "未找到该患者的病历记录");
  }

  async function handleList() {
    setCurrentSearchPatient(null);
    await listEmrsByPatientId(patientId.trim());
  }

  async function handleGlobalSearch() {
    const query = globalQuery.trim();
    if (!query) {
      setSearchMessage("请输入姓名 / 手机号 / 病历号 / 患者ID");
      return;
    }
    setSearching(true);
    setSearchResults([]);
    setSearchMessage("");

    const isEmrId = /^emr[-_]/i.test(query);
    const isPatientId = /^p[a-z0-9]{6,}$/i.test(query);
    const isRecordId = /^(rec|record)[-_]?/i.test(query);

    try {
      if (isEmrId) {
        setEmrId(query);
        await fetchEmrById(query);
        setSearchMessage("已按病历 ID 查询");
        return;
      }

      if (isPatientId) {
        setPatientId(query);
        const ok = await fetchLatestEmrForPatient(query);
        setSearchMessage(ok ? "已读取患者最近病例" : "未找到该患者的病历记录");
        return;
      }

      if (isRecordId) {
        setRecordId(query);
        await generateEmrByRecordId(query);
        setSearchMessage("已按采集记录 ID 生成报告");
        return;
      }

      const response = await fetch(`${API_BASE}/patients?page=1&limit=10000&include_archived=true`);
      const data = (await response.json()) as PatientSearchResult[];
      const candidates = Array.isArray(data) ? data : [];
      const keyword = query.toLowerCase();
      const matches = candidates.filter((patient) => {
        const fields = [
          patient.patient_id,
          patient.name,
          patient.phone,
          patient.id_card,
        ]
          .filter(Boolean)
          .map((value) => String(value).toLowerCase());
        return fields.some((value) => value.includes(keyword));
      });

      if (matches.length === 1) {
        const target = matches[0];
        setCurrentSearchPatient(target);
        setPatientId(target.patient_id);
        const ok = await fetchLatestEmrForPatient(target.patient_id);
        setSearchMessage(
          ok
            ? `已定位患者：${target.name || target.patient_id}，并读取最近病例`
            : `已定位患者：${target.name || target.patient_id}，但未找到病例`
        );
        return;
      }

      if (matches.length > 1) {
        setSearchResults(matches.slice(0, 8));
        setCurrentSearchPatient(null);
        setSearchMessage(`找到 ${matches.length} 位患者，请从下方选择`);
        return;
      }

      setSearchMessage("未找到匹配患者，请确认输入信息");
    } catch (error) {
      setSearchMessage(`搜索失败: ${String(error)}`);
    } finally {
      setSearching(false);
    }
  }

  async function handleSelectSearchResult(patient: PatientSearchResult) {
    if (!patient.patient_id) return;
    setCurrentSearchPatient(patient);
    setPatientId(patient.patient_id);
    const ok = await fetchLatestEmrForPatient(patient.patient_id);
    setSearchResults([]);
    setSearchMessage(
      ok
        ? `已定位患者：${patient.name || patient.patient_id}，并读取最近病例`
        : `已定位患者：${patient.name || patient.patient_id}，但未找到病例`
    );
    flashSuccessButton();
  }

  async function handleSave() {
    if (!emrId.trim()) {
      setOutput({ error: "请先获取病历" });
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/emr/${emrId.trim()}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          diagnosis,
          doctor_opinion: doctorOpinion,
        }),
      });
      if (!response.ok) {
        const text = await response.text();
        setOutput({ error: `保存失败: ${response.status} ${text || response.statusText}` });
        return;
      }
      const data = (await response.json()) as EmrResponse;
      setOutput(data);
      syncEmrFields(data);
      setReport(extractReport(data));
      fetchReports();
      flashSuccessButton();
    } catch (error) {
      setOutput({ error: `保存失败: ${String(error)}` });
    }
  }

  async function handleArchive(nextArchived: boolean) {
    if (!emrId.trim()) {
      setOutput({ error: "请先获取病历" });
      return;
    }
    const data = await postJson(`${API_BASE}/emr/${emrId.trim()}/archive`, {
      archived: nextArchived,
    });
    setOutput(data as EmrResponse);
    syncEmrFields(data as EmrResponse);
    setReport(extractReport(data as EmrResponse));
    flashSuccessButton();
  }

  function handleExportReportJson() {
    if (!report) {
      setOutput({ error: "暂无可导出的报告" });
      return;
    }
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `report-${emrId || recordId || "export"}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    flashSuccessButton();
  }

  function handleExportPdf() {
    if (!report) {
      setOutput({ error: "暂无可导出的报告" });
      return;
    }

    const patient = report.patient && typeof report.patient === "object"
      ? (report.patient as Record<string, unknown>)
      : {};
    const analysis = report.analysis && typeof report.analysis === "object"
      ? (report.analysis as Record<string, unknown>)
      : {};
    const metrics = analysis.temperature_metrics && typeof analysis.temperature_metrics === "object"
      ? (analysis.temperature_metrics as Record<string, unknown>)
      : {};

    const html = `
      <!doctype html>
      <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <title>红外热成像诊断报告</title>
        <style>
          body { font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif; margin: 32px; color: #0f172a; }
          h1 { text-align: center; margin-bottom: 24px; }
          h2 { margin: 24px 0 12px; font-size: 16px; }
          .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
          .card { border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; background: #f8fafc; }
          .label { color: #64748b; font-size: 12px; }
          .value { font-weight: 600; margin-top: 4px; }
          .section { margin-top: 16px; }
          .text { line-height: 1.6; white-space: pre-wrap; }
          .risk { font-weight: 700; text-transform: uppercase; }
          @media print { body { margin: 18mm; } }
        </style>
      </head>
      <body>
        <h1>红外热成像诊断报告</h1>
        <div class="grid">
          <div class="card"><div class="label">报告ID</div><div class="value">${String(report.report_id || "-")}</div></div>
          <div class="card"><div class="label">采集时间</div><div class="value">${String(report.created_at || "-")}</div></div>
        </div>

        <div class="section">
          <h2>患者信息</h2>
          <div class="grid">
            <div class="card"><div class="label">姓名</div><div class="value">${String(patient.name || "-")}</div></div>
            <div class="card"><div class="label">性别/年龄</div><div class="value">${formatGender(String(patient.gender || "-"))} / ${String(patient.age || "-")}</div></div>
            <div class="card"><div class="label">采集部位</div><div class="value">${String(patient.body_part || "-")}</div></div>
            <div class="card"><div class="label">风险等级</div><div class="value risk">${String(analysis.risk_level || "-")}</div></div>
          </div>
        </div>

        <div class="section">
          <h2>温度指标</h2>
          <div class="grid">
            <div class="card"><div class="label">最低温度</div><div class="value">${String(metrics.min_c ?? "-")}°C</div></div>
            <div class="card"><div class="label">最高温度</div><div class="value">${String(metrics.max_c ?? "-")}°C</div></div>
            <div class="card"><div class="label">平均温度</div><div class="value">${String(metrics.avg_c ?? "-")}°C</div></div>
          </div>
        </div>

        <div class="section">
          <h2>诊断结论</h2>
          <div class="text">${String(report.diagnosis || "-")}</div>
        </div>

        <div class="section">
          <h2>医生意见</h2>
          <div class="text">${String(report.doctor_opinion || "-")}</div>
        </div>
      </body>
      </html>
    `;

    printHtmlInIframe(html);
    flashSuccessButton();
  }

  function handlePrint() {
    window.print();
    flashSuccessButton();
  }

  function printHtmlInIframe(html: string) {
    const iframe = document.createElement("iframe");
    iframe.style.position = "fixed";
    iframe.style.right = "0";
    iframe.style.bottom = "0";
    iframe.style.width = "0";
    iframe.style.height = "0";
    iframe.style.border = "0";
    iframe.setAttribute("aria-hidden", "true");
    document.body.appendChild(iframe);

    const cleanup = () => {
      iframe.remove();
    };

    const frameDoc = iframe.contentWindow?.document;
    if (!frameDoc) {
      cleanup();
      setOutput({ error: "无法打开打印窗口" });
      return;
    }

    frameDoc.open();
    frameDoc.write(html);
    frameDoc.close();

    iframe.onload = () => {
      try {
        iframe.contentWindow?.focus();
        iframe.contentWindow?.print();
      } finally {
        setTimeout(cleanup, 0);
      }
    };
  }

  async function handleViewDocx(url: string) {
    const lowerUrl = String(url || "").toLowerCase();
    if (!lowerUrl.endsWith(".docx")) {
      // Force browser inline preview for PDF and other non-docx reports.
      const toInlinePreviewUrl = (rawUrl: string) => {
        const raw = String(rawUrl || "").trim();
        if (!raw) return "/api/reports";
        if (raw.startsWith("/reports/preview")) return `/api${raw}`;

        const match = raw.match(/^\/reports\/([^/]+)\/(.+)$/);
        if (!match) return `/api${raw}`;

        const safeDecode = (value: string) => {
          try {
            return decodeURIComponent(value);
          } catch {
            return value;
          }
        };

        const date = encodeURIComponent(safeDecode(match[1]));
        const filename = encodeURIComponent(safeDecode(match[2]));
        return `/api/reports/preview?date=${date}&filename=${filename}`;
      };

      const previewUrl = toInlinePreviewUrl(url);
      const popup = window.open(previewUrl, "_blank", "noopener,noreferrer");
      if (!popup) {
        window.location.href = previewUrl;
      }
      return;
    }

    try {
      const proxyUrl = `/api${url}`;
      const response = await fetch(proxyUrl, { cache: "no-store" });
      const arrayBuffer = await response.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer });
      setPreviewHtml(result.value);
      setShowPreview(true);
      flashSuccessButton();
    } catch (error) {
      setOutput({ error: `预览失败: ${String(error)}` });
    }
  }

  async function handlePrintDocx(url: string) {
    const lowerUrl = String(url || "").toLowerCase();
    if (!lowerUrl.endsWith(".docx")) {
      const toInlinePreviewUrl = (rawUrl: string) => {
        const raw = String(rawUrl || "").trim();
        if (!raw) return "/api/reports";
        if (raw.startsWith("/reports/preview")) return `/api${raw}`;

        const match = raw.match(/^\/reports\/([^/]+)\/(.+)$/);
        if (!match) return `/api${raw}`;

        const safeDecode = (value: string) => {
          try {
            return decodeURIComponent(value);
          } catch {
            return value;
          }
        };

        const date = encodeURIComponent(safeDecode(match[1]));
        const filename = encodeURIComponent(safeDecode(match[2]));
        return `/api/reports/preview?date=${date}&filename=${filename}`;
      };

      const previewUrl = toInlinePreviewUrl(url);
      const popup = window.open(previewUrl, "_blank", "noopener,noreferrer");
      if (!popup) {
        window.location.href = previewUrl;
      }
      return;
    }

    try {
      const proxyUrl = `/api${url}`;
      const response = await fetch(proxyUrl, { cache: "no-store" });
      const arrayBuffer = await response.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer });
      printHtmlInIframe(`
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <title>打印报告</title>
          <style>
            body { font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif; margin: 24px; }
            .prose { max-width: 100%; }
          </style>
        </head>
        <body>
          <div class="prose">${result.value}</div>
        </body>
        </html>
      `);
      flashSuccessButton();
    } catch (error) {
      setOutput({ error: `打印失败: ${String(error)}` });
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#f4f1ea]">
      {incomingEmrToast && (
        <div className="fixed right-6 top-20 z-50 w-[22rem] rounded-2xl border border-emerald-200 bg-white p-4 shadow-xl">
          <p className="text-sm font-semibold text-emerald-700">生成成功</p>
          <p className="mt-1 text-sm text-slate-700">{incomingEmrToast.message}</p>
          <div className="mt-3 flex items-center gap-2">
            <button
              className="rounded-full bg-emerald-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
              onClick={jumpToIncomingEmr}
            >
              一键跳转到新病历
            </button>
            <button
              className="rounded-full border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50"
              onClick={() => setIncomingEmrToast(null)}
            >
              关闭
            </button>
          </div>
        </div>
      )}
      <div className="pointer-events-none absolute -top-32 right-[-10%] h-80 w-80 rounded-full bg-amber-200/50 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 left-[-10%] h-96 w-96 rounded-full bg-sky-200/50 blur-3xl" />
      <main
        className="relative mx-auto flex min-h-screen max-w-7xl flex-col gap-10 px-6 py-12"
        style={{ fontFamily: '"Avenir Next", "PingFang SC", "Microsoft YaHei", sans-serif' }}
      >
        <header className="grid items-end gap-8 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="space-y-4 hero-fade">
            <p className="text-xs uppercase tracking-[0.35em] text-amber-700">Clinical Intelligence</p>
            <h1 className="text-4xl font-semibold text-slate-900 sm:text-5xl">
              患者数据分析与统计中心
            </h1>
            <p className="max-w-2xl text-base text-slate-700">
              医生可在此完成病历生成、趋势分析、诊断报告管理，并快速定位异常区域与风险等级。
            </p>
            <div className="flex flex-wrap gap-3">
              <button
                className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
                onClick={handleFetchLatestForPatient}
              >
                一键读取患者最近病例
              </button>
              <button
                className="rounded-full border border-slate-300 bg-white/80 px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-white"
                onClick={handleExportReportJson}
              >
                导出报告 JSON
              </button>
              {report && (
                <button
                  className="rounded-full border border-slate-300 bg-white/80 px-5 py-2 text-sm font-semibold text-slate-700 hover:bg-white"
                  onClick={() => router.push("/treatment")}
                >
                  生成治疗方案
                </button>
              )}
            </div>

            <div className="mt-6 rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-900">统一搜索</p>
                <span className="text-xs text-slate-500">姓名 / 手机号 / 病历号 / 患者ID</span>
              </div>
              <div className="mt-3 flex flex-col gap-3 sm:flex-row">
                <input
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  placeholder="例如：张三 / 13800000000 / EMR-xxxx / Pxxxx"
                  value={globalQuery}
                  onChange={(event) => setGlobalQuery(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      handleGlobalSearch();
                    }
                  }}
                />
                <button
                  className="rounded-full bg-amber-600 px-5 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:bg-amber-300 whitespace-nowrap"
                  onClick={handleGlobalSearch}
                  disabled={searching}
                >
                  {searching ? "搜索中..." : "搜索"}
                </button>
              </div>
              {searchMessage && (
                <p className="mt-2 text-xs text-slate-600">{searchMessage}</p>
              )}
              {searchResults.length > 0 && (
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {searchResults.map((patient) => (
                    <button
                      key={patient.patient_id}
                      className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 text-left hover:bg-slate-50"
                      onClick={() => handleSelectSearchResult(patient)}
                    >
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {patient.name || "未命名患者"}
                        </p>
                        <p className="text-xs text-slate-500">
                          患者ID：{patient.patient_id}
                          {patient.phone ? ` · ${patient.phone}` : ""}
                        </p>
                      </div>
                      <span className="text-xs font-semibold text-amber-700">打开 →</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {(ingestRunning || ingestProgress > 0) && (
              <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50/95 p-4 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-emerald-900">数据分析进度</p>
                  <span className="text-xs font-semibold text-emerald-700">{Math.round(ingestProgress)}%</span>
                </div>
                <div className="mt-2 h-2 w-full rounded-full bg-emerald-200">
                  <div
                    className="h-2 rounded-full bg-emerald-600 transition-all duration-300"
                    style={{ width: `${Math.max(0, Math.min(100, ingestProgress))}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-emerald-800">
                  {ingestStatus || "分析准备中..."}
                  {recordId.trim() ? `（record_id: ${recordId.trim()}）` : ""}
                </p>
                {ingestStep > 0 && (
                  <p className="mt-1 text-xs text-emerald-700">当前阶段：步骤 {ingestStep}</p>
                )}
              </div>
            )}
          </div>

          <div className="rounded-3xl bg-white/90 p-5 shadow-sm ring-1 ring-amber-200/60 backdrop-blur hero-fade">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-slate-900">当前患者概览</p>
              <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-semibold text-amber-700">
                {archived ? "已存档" : "活跃"}
              </span>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-slate-200/80 bg-white px-3 py-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">姓名</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{patientSummary.name}</p>
              </div>
              <div className="rounded-xl border border-slate-200/80 bg-white px-3 py-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">性别 / 年龄</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">
                  {patientSummary.gender} / {patientSummary.age}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200/80 bg-white px-3 py-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">病历 ID</p>
                <p className="mt-1 truncate text-sm font-semibold text-slate-900">{emrId || "-"}</p>
              </div>
              <div className="rounded-xl border border-slate-200/80 bg-white px-3 py-2">
                <p className="text-xs uppercase tracking-wide text-slate-400">采集部位</p>
                <p className="mt-1 text-sm font-semibold text-slate-900">{patientSummary.bodyPart}</p>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-600">
              <span className="rounded-full bg-slate-100 px-3 py-1">患者 ID：{patientId || "-"}</span>
              <span className="rounded-full bg-slate-100 px-3 py-1">最近报告：{overview.latestReportLabel}</span>
            </div>
          </div>
        </header>

        <section className="grid gap-4 lg:grid-cols-4">
          <div className="rounded-2xl bg-white/90 p-5 shadow-sm ring-1 ring-slate-200/80 lift-1">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">风险等级</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">{overview.riskLevel}</p>
            <p className="mt-1 text-xs text-slate-500">高风险患者自动标记</p>
          </div>
          <div className="rounded-2xl bg-white/90 p-5 shadow-sm ring-1 ring-slate-200/80 lift-1">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">异常区域</p>
            <button
              className="mt-2 inline-flex items-center gap-2 text-2xl font-semibold text-slate-900"
              onClick={() => {
                if (overview.abnormalCount > 0) {
                  setShowAbnormalDetails(true);
                }
              }}
              disabled={overview.abnormalCount === 0}
            >
              {overview.abnormalCount}
              <span className="text-xs font-semibold text-amber-700">
                {overview.abnormalCount > 0 ? "查看" : ""}
              </span>
            </button>
            <p className="mt-1 text-xs text-slate-500">可用于后续复诊追踪</p>
          </div>
          <div className="rounded-2xl bg-white/90 p-5 shadow-sm ring-1 ring-slate-200/80 lift-2">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">温度范围</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">{overview.tempRange}</p>
            <p className="mt-1 text-xs text-slate-500">基于热成像采样</p>
          </div>
          <div className="rounded-2xl bg-white/90 p-5 shadow-sm ring-1 ring-slate-200/80 lift-2">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">报告总数</p>
            <button
              className="mt-2 inline-flex items-center gap-2 text-2xl font-semibold text-slate-900"
              onClick={() => {
                const target = document.getElementById("report-history");
                if (target) {
                  target.scrollIntoView({ behavior: "smooth", block: "start" });
                }
              }}
            >
              {overview.reportCount}
              <span className="text-xs font-semibold text-amber-700">查看</span>
            </button>
            <p className="mt-1 text-xs text-slate-500">覆盖历史诊断数据</p>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-12">
          <div className="rounded-3xl bg-white/90 p-6 shadow-sm ring-1 ring-slate-200/80 lg:col-span-5">
            <h2 className="text-lg font-semibold text-slate-900">生成诊断报告</h2>
            <label className="mt-4 block text-sm font-medium text-slate-700">
              记录 ID (record_id)
            </label>
            <input
              className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              placeholder="请输入 record_id"
              value={recordId}
              onChange={(event) => setRecordId(event.target.value)}
            />
            <button
              className="mt-4 w-full rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              onClick={handleGenerate}
            >
              生成诊断报告
            </button>
            <p className="mt-3 text-xs text-slate-500">
              将基于采集数据自动生成诊断报告，并同步分析指标。
            </p>
          </div>

          <div className="grid gap-6 lg:col-span-7 sm:grid-cols-2">
            <div className="rounded-3xl bg-white/90 p-6 shadow-sm ring-1 ring-slate-200/80">
              <h2 className="text-lg font-semibold text-slate-900">查询病历</h2>
              <label className="mt-4 block text-sm font-medium text-slate-700">
                病历 ID (emr_id)
              </label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="请输入 emr_id"
                value={emrId}
                onChange={(event) => setEmrId(event.target.value)}
              />
              <button
                className="mt-4 w-full rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                onClick={handleFetch}
              >
                获取病历
              </button>
            </div>

            <div className="rounded-3xl bg-white/90 p-6 shadow-sm ring-1 ring-slate-200/80">
              <h2 className="text-lg font-semibold text-slate-900">按患者查询</h2>
              <label className="mt-4 block text-sm font-medium text-slate-700">
                患者 ID (patient_id)
              </label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                placeholder="请输入 patient_id"
                value={patientId}
                onChange={(event) => setPatientId(event.target.value)}
              />
              <button
                className="mt-4 w-full rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                onClick={handleList}
              >
                查询
              </button>
            </div>
          </div>
        </section>

        <section
          id="report-history"
          className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-slate-900">诊断报告</h2>
          </div>
          {report ? (
            <div className="mt-4 space-y-6">
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">报告ID</p>
                  <p className="mt-1 font-mono text-sm text-slate-900">
                    {String(report.report_id ?? "-")}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">采集时间</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {String(report.created_at ?? "-")}
                  </p>
                </div>
                {Boolean(report.analysis && typeof report.analysis === "object") && (
                  <div className="rounded-xl border border-slate-200 bg-blue-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-blue-600">风险等级</p>
                    <p className="mt-1 text-lg font-bold uppercase text-blue-900">
                      {String((report.analysis as Record<string, unknown>).risk_level ?? "-")}
                    </p>
                  </div>
                )}
              </div>

              {Boolean(
                report.analysis &&
                typeof report.analysis === "object" &&
                (report.analysis as Record<string, unknown>).temperature_metrics
              ) && (
                <div className="rounded-xl border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-900">温度指标</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-4">
                    {Object.entries((report.analysis as Record<string, unknown>).temperature_metrics as Record<string, unknown>).map(([key, value]) => (
                      <div key={key} className="rounded-lg bg-slate-50 p-3">
                        <p className="text-xs text-slate-500">{formatTemperatureMetricLabel(key)}</p>
                        <p className="mt-1 text-base font-semibold text-slate-900">{String(value)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {Boolean(
                report.analysis &&
                typeof report.analysis === "object" &&
                Boolean((report.analysis as Record<string, unknown>).roi_analysis) &&
                typeof (report.analysis as Record<string, unknown>).roi_analysis === "object" &&
                Boolean(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).roi_list) &&
                Array.isArray(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).roi_list) &&
                (((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).roi_list as unknown[]).length > 0
              ) && (
                <div className="rounded-xl border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-900">姿态分区温度（ROI）</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-3">
                    <div className="rounded-lg bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">识别区域数</p>
                      <p className="mt-1 text-base font-semibold text-slate-900">
                        {String(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).total_rois ?? "-")}
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">最热区域</p>
                      <p className="mt-1 text-base font-semibold text-slate-900">
                        {formatRoiLabel(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).hottest_region)}
                        {" "}
                        ({String(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).hottest_temp ?? "-")}°C)
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-3">
                      <p className="text-xs text-slate-500">最冷区域</p>
                      <p className="mt-1 text-base font-semibold text-slate-900">
                        {formatRoiLabel(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).coolest_region)}
                        {" "}
                        ({String(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).coolest_temp ?? "-")}°C)
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 space-y-2">
                    {(((report.analysis as Record<string, unknown>).roi_analysis as Record<string, unknown>).roi_list as Record<string, unknown>[]).map((roi, idx) => (
                      <div
                        key={`${String(roi.name || "roi")}-${idx}`}
                        className="grid gap-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700 sm:grid-cols-6"
                      >
                        <div className="font-medium text-slate-900">{formatRoiLabel(roi.name)}</div>
                        <div>均值 {String(roi.mean_c ?? "-")}°C</div>
                        <div>最低 {String(roi.min_c ?? "-")}°C</div>
                        <div>最高 {String(roi.max_c ?? "-")}°C</div>
                        <div>标准差 {String(roi.std_c ?? "-")}</div>
                        <div>样本 {String(roi.count ?? "-")}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="rounded-xl border border-slate-200 p-4">
                <h3 className="text-sm font-semibold text-slate-900">诊断结论</h3>
                <p className="mt-2 text-slate-700">
                  {String(report.diagnosis ?? "-")}
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 p-4">
                <h3 className="text-sm font-semibold text-slate-900">医生意见</h3>
                <p className="mt-2 text-slate-700">
                  {String(report.doctor_opinion ?? "-")}
                </p>
              </div>

              {Boolean(
                report.analysis &&
                typeof report.analysis === "object" &&
                (report.analysis as Record<string, unknown>).regional_comparison &&
                typeof (report.analysis as Record<string, unknown>).regional_comparison === "object" &&
                ((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions &&
                Array.isArray(((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions) &&
                (((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions as unknown[]).length > 0
              ) && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <h3 className="text-sm font-semibold text-amber-900">异常区域</h3>
                  <div className="mt-3 space-y-2">
                    {(((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions as Record<string, unknown>[]).map((region, idx) => (
                      <div key={idx} className="flex items-center justify-between rounded-lg bg-white p-3">
                        <span className="font-mono text-sm text-slate-700">
                          {formatRegionLabel(region.region)}
                        </span>
                        <span className={`text-xs font-semibold uppercase ${
                          region.status === "high" ? "text-red-600" : "text-blue-600"
                        }`}>
                          {String(region.status)}
                        </span>
                        <span className="text-sm text-slate-900">{String(region.avg_c)}°C</span>
                        <span className="text-sm text-slate-600">Δ {String(region.delta_c)}°C</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <p className="mt-4 text-sm text-slate-500">暂无报告数据</p>
          )}
        </section>

        {(thermalImageUrl || uploadedThermalImageUrls.length > 0) && (
          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">热成像图</h2>

            {/* Original uploaded thermal images grid */}
            {uploadedThermalImageUrls.length > 0 && (
              <div className="mt-4">
                <p className="mb-3 text-xs text-slate-500">
                  原始上传图片（共 {uploadedThermalImageUrls.length} 张）
                </p>
                <div className={`grid gap-3 ${uploadedThermalImageUrls.length === 1 ? "grid-cols-1" : uploadedThermalImageUrls.length === 2 ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3"}`}>
                  {uploadedThermalImageUrls.map((url, idx) => (
                    <img
                      key={url}
                      src={url}
                      alt={`热成像图 ${idx + 1}`}
                      className="w-full rounded-xl border border-slate-200 object-contain"
                    />
                  ))}
                </div>
              </div>
            )}

            {/* Generated heatmap with ROI overlay */}
            {thermalImageUrl && (
              <div className="mt-5">
                <p className="mb-3 text-xs text-slate-500">已叠加人体部位温度标签（头部标签自动避让，基于 ROI 分析）</p>
                <div className="relative w-full max-w-2xl">
                  <img
                    src={thermalImageUrl}
                    alt="Thermal Marked Image"
                    className="w-full max-w-2xl rounded-xl border border-slate-200"
                  />
                  <svg className="pointer-events-none absolute inset-0 z-10 h-full w-full">
                    {roiOverlayLayoutPoints.map((point, index) => {
                      if (!point.showLeader) {
                        return null;
                      }
                      const edgeX = point.labelX <= point.x ? point.labelX + 4.5 : point.labelX - 4.5;
                      return (
                        <line
                          key={`line-${point.name}-${index}`}
                          x1={`${point.x}%`}
                          y1={`${point.y}%`}
                          x2={`${edgeX}%`}
                          y2={`${point.labelY}%`}
                          stroke="rgba(15, 23, 42, 0.85)"
                          strokeWidth="1"
                        />
                      );
                    })}
                  </svg>
                  {roiOverlayLayoutPoints.map((point, index) => (
                    <div
                      key={`${point.name}-${index}`}
                      className="pointer-events-none absolute z-20 -translate-x-1/2 -translate-y-1/2 rounded-md border border-white/30 bg-slate-900/70 px-2 py-1 text-[11px] font-semibold text-white"
                      style={{ left: `${point.labelX}%`, top: `${point.labelY}%` }}
                    >
                      {point.name} {point.meanC.toFixed(1)}°C
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        )}

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">历史报告文件</h2>
            <button
              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              onClick={() => setShowAllReports((prev) => !prev)}
            >
              {showAllReports ? "仅看当前患者" : "显示全部"}
            </button>
          </div>
          {reportFiles.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">暂无报告文件</p>
          ) : (
            <>
              {!currentPatientName && (
                <p className="mt-3 text-sm text-amber-600">
                  未识别患者姓名，已显示全部历史报告。
                </p>
              )}
              {currentPatientName && visibleReportFiles.length === 0 && (
                <p className="mt-3 text-sm text-amber-600">
                  未匹配到患者“{currentPatientName}”的报告文件，已显示全部历史报告。
                </p>
              )}
              <div className="mt-4 overflow-hidden rounded-xl border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-2 font-medium">日期</th>
                      <th className="px-4 py-2 font-medium">文件名</th>
                      <th className="px-4 py-2 font-medium">大小</th>
                      <th className="px-4 py-2 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {paginatedReportFiles.map((file) => (
                      <tr key={`${file.date}-${file.name}`}>
                        <td className="px-4 py-2 text-slate-700">{file.date}</td>
                        <td className="px-4 py-2 text-slate-900">{file.name}</td>
                        <td className="px-4 py-2 text-slate-700">
                          {(file.size_bytes / 1024).toFixed(1)} KB
                        </td>
                        <td className="px-4 py-2">
                          <div className="flex flex-wrap gap-2">
                            <button
                              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                              onClick={() => handleViewDocx(file.url)}
                            >
                              查看
                            </button>
                            <a
                              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                              href={`/api${file.url}`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              下载
                            </a>
                            <button
                              className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                              onClick={() => handlePrintDocx(file.url)}
                            >
                              打印
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  第 {reportPage} / {reportTotalPages} 页，共 {reportFilesForDisplay.length} 份报告
                </p>
                <div className="flex items-center gap-2">
                  <button
                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={() => setReportPage((prev) => Math.max(1, prev - 1))}
                    disabled={reportPage <= 1}
                  >
                    上一页
                  </button>
                  <button
                    className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={() => setReportPage((prev) => Math.min(reportTotalPages, prev + 1))}
                    disabled={reportPage >= reportTotalPages}
                  >
                    下一页
                  </button>
                </div>
              </div>
            </>
          )}
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">编辑 / 导出 / 存档</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700">初步诊断</label>
              <textarea
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                rows={3}
                value={diagnosis}
                onChange={(event) => setDiagnosis(event.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">医生意见</label>
              <textarea
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                rows={3}
                value={doctorOpinion}
                onChange={(event) => setDoctorOpinion(event.target.value)}
              />
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-3">
            <button
              className="rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              onClick={handleSave}
            >
              保存修改
            </button>
            <button
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              onClick={handleExportPdf}
            >
              导出 PDF
            </button>
            <button
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              onClick={handlePrint}
            >
              打印
            </button>
            <button
              className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              onClick={() => handleArchive(!archived)}
            >
              {archived ? "取消存档" : "存档"}
            </button>
          </div>
        </section>

        {showPreview && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setShowPreview(false)}
          >
            <div
              className="relative max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl bg-white p-6 shadow-xl"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                className="absolute right-4 top-4 rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                onClick={() => {
                  setShowPreview(false);
                  flashSuccessButton();
                }}
              >
                关闭
              </button>
              <div
                className="prose max-w-none"
                dangerouslySetInnerHTML={{ __html: previewHtml }}
              />
            </div>
          </div>
        )}
        {showAbnormalDetails && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            onClick={() => setShowAbnormalDetails(false)}
          >
            <div
              className="relative max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-6 shadow-xl"
              onClick={(event) => event.stopPropagation()}
            >
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-slate-900">异常区域明细</h3>
                <button
                  className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                  onClick={() => setShowAbnormalDetails(false)}
                >
                  关闭
                </button>
              </div>
              {abnormalRegionList.length === 0 ? (
                <p className="mt-4 text-sm text-slate-500">暂无异常区域数据</p>
              ) : (
                <div className="mt-4 space-y-2">
                  {abnormalRegionList.map((region, index) => (
                    <div
                      key={`${String(region.region || "region")}-${index}`}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4"
                    >
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {formatRegionLabel(region.region || "未命名区域")}
                        </p>
                        <p className="text-xs text-slate-500">
                          平均温度 {String(region.avg_c ?? "-")}°C · Δ {String(region.delta_c ?? "-")}°C
                        </p>
                      </div>
                      <span
                        className={`rounded-full px-3 py-1 text-xs font-semibold uppercase ${
                          region.status === "high"
                            ? "bg-rose-100 text-rose-700"
                            : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        {String(region.status || "normal")}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
        <style jsx>{`
          @keyframes fadeUp {
            from {
              opacity: 0;
              transform: translateY(16px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
          .hero-fade {
            animation: fadeUp 0.8s ease both;
          }
          .lift-1 {
            animation: fadeUp 0.9s ease both;
            animation-delay: 0.08s;
          }
          .lift-2 {
            animation: fadeUp 0.9s ease both;
            animation-delay: 0.16s;
          }
          @media (prefers-reduced-motion: reduce) {
            .hero-fade,
            .lift-1,
            .lift-2 {
              animation: none;
            }
          }
        `}</style>
      </main>
    </div>
  );
}

export default function EmrPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-500">加载中...</div>}>
      <EmrPageContent />
    </Suspense>
  );
}
