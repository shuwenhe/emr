"use client";

export const dynamic = "force-dynamic";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { flashSuccessButton } from "../lib/flash";

type Patient = {
  patient_id: string;
  name: string;
  gender: string;
  age: number;
};

const API_PROXY_BASE = "/api";
const API_BACKEND_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const UPLOAD_STATE_KEY = "patient_flow_state_upload";

function getCurrentDateTimeLocalValue() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  const y = now.getFullYear();
  const m = pad(now.getMonth() + 1);
  const d = pad(now.getDate());
  const hh = pad(now.getHours());
  const mm = pad(now.getMinutes());
  return `${y}-${m}-${d}T${hh}:${mm}`;
}

function normalizeCaptureTime(value: string) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  // datetime-local typically returns YYYY-MM-DDTHH:mm; backend expects seconds.
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(trimmed)) {
    return `${trimmed}:00`;
  }
  return trimmed;
}

function UploadPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [files, setFiles] = useState<File[]>([]);
  const [deviceId, setDeviceId] = useState("device-001");
  const [deviceModel, setDeviceModel] = useState("IR-Thermal-320");
  const [captureTime, setCaptureTime] = useState(getCurrentDateTimeLocalValue());
  const [patientName, setPatientName] = useState("");
  const [gender, setGender] = useState("");
  const [age, setAge] = useState("");
  const [bodyPart, setBodyPart] = useState("全身");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ record_id?: string; error?: string } | null>(null);
  const [patientMode, setPatientMode] = useState<"new" | "existing">("new");
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");

  function formatGender(value?: string) {
    if (!value) return "-";
    const normalized = String(value).toLowerCase();
    if (normalized === "male" || normalized === "m" || value === "男") return "男";
    if (normalized === "female" || normalized === "f" || value === "女") return "女";
    return String(value);
  }
  const [patientsLoading, setPatientsLoading] = useState(true);
  const [patientsError, setPatientsError] = useState("");
  const [patientsWarming, setPatientsWarming] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState("");
  const [uploadCompleted, setUploadCompleted] = useState(false);
  const [reportGenerating, setReportGenerating] = useState(false);
  const [reportProgress, setReportProgress] = useState(0);
  const [reportStatus, setReportStatus] = useState("");
  const [currentStep, setCurrentStep] = useState(0);
  const autoSelectedFromUrlRef = useRef(false);
  const warmingRetryRef = useRef(0);
  const MAX_WARMING_RETRIES = 200; // 200 × 3 s ≈ 10 min max wait

  function uploadFormDataWithProgress(url: string, formData: FormData): Promise<{ ok: boolean; status: number; data: any }> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      let receivedNativeProgress = false;
      const fallbackTimer = window.setInterval(() => {
        if (receivedNativeProgress) return;
        setUploadProgress((prev) => {
          const next = Math.max(prev, 3);
          return next >= 18 ? next : next + 1;
        });
        setUploadStatus("正在上传数据文件...");
      }, 250);

      const clearFallbackTimer = () => {
        window.clearInterval(fallbackTimer);
      };

      xhr.open("POST", url, true);
      xhr.responseType = "json";
      // Upload can queue briefly behind local file I/O or large batch writes.
      // Keep the browser request alive long enough for the backend to return a
      // record_id quickly, then remaining analysis continues in the background.
      xhr.timeout = 600000;

      xhr.onloadstart = () => {
        setUploadProgress((prev) => Math.max(prev, 3));
        setUploadStatus("正在建立上传连接...");
      };

      xhr.upload.onprogress = (event) => {
        receivedNativeProgress = true;
        clearFallbackTimer();
        if (!event.lengthComputable || event.total <= 0) return;
        const pct = Math.max(0, Math.min(99, Math.round((event.loaded / event.total) * 100)));
        setUploadProgress(pct);
        setUploadStatus(`正在上传数据文件... ${pct}%`);
      };

      xhr.onload = () => {
        clearFallbackTimer();
        const raw = xhr.response;
        const data = typeof raw === "string"
          ? (() => {
              try {
                return JSON.parse(raw);
              } catch {
                return {};
              }
            })()
          : (raw || {});
        resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data });
      };

      xhr.onerror = () => {
        clearFallbackTimer();
        reject(new Error("网络连接失败，上传中断"));
      };
      xhr.ontimeout = () => {
        clearFallbackTimer();
        reject(new Error("上传超时，请检查后端服务状态或稍后重试"));
      };
      xhr.onabort = () => {
        clearFallbackTimer();
        reject(new Error("上传已取消"));
      };
      xhr.send(formData);
    });
  }

  useEffect(() => {
    fetchPatients();
  }, []);

  async function fetchPatients(isWarmingRetry = false) {
    if (!isWarmingRetry) {
      warmingRetryRef.current = 0;
      setPatientsLoading(true);
      setPatientsError("");
      setPatientsWarming(false);
    }
    try {
      const response = await fetch(`${API_PROXY_BASE}/patients`, {
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const cacheStatus = response.headers.get("x-cache");
      const data = await response.json();

      if (cacheStatus === "WARMING") {
        // Backend not ready yet — silently retry every 3 s
        warmingRetryRef.current += 1;
        if (warmingRetryRef.current === 4) setPatientsWarming(true); // hint after ~12 s
        if (warmingRetryRef.current <= MAX_WARMING_RETRIES) {
          window.setTimeout(() => fetchPatients(true), 3000);
          return; // stay in loading state, no error shown
        }
        // Gave up after ~10 min — show error with retry button
        setPatientsError("服务响应超时，请检查后端服务是否正常运行");
        setPatients([]);
        setPatientsWarming(false);
        setPatientsLoading(false);
        return;
      }

      warmingRetryRef.current = 0;
      setPatientsWarming(false);
      setPatients(Array.isArray(data) ? data : []);
      setPatientsLoading(false);
    } catch (error) {
      console.error("Failed to fetch patients:", error);
      setPatientsError(
        error instanceof Error ? error.message : String(error)
      );
      setPatients([]);
      setPatientsWarming(false);
      setPatientsLoading(false);
    }
  }

  // Auto-select patient when navigated from self-register QR flow
  useEffect(() => {
    if (autoSelectedFromUrlRef.current) return;
    const patientId = searchParams.get("patient_id");
    if (patientId && patients.length > 0) {
      autoSelectedFromUrlRef.current = true;
      setPatientMode("existing");
      setSelectedPatientId(patientId);
      const patient = patients.find(p => p.patient_id === patientId);
      if (patient) {
        setPatientName(patient.name);
        const gv = patient.gender === "男" ? "male" : patient.gender === "女" ? "female" : patient.gender;
        setGender(gv);
        setAge(String(patient.age));
      }
    }
  }, [patients, searchParams]);

  useEffect(() => {
    const name = searchParams.get("name") || "";
    const genderParam = searchParams.get("gender") || "";
    const ageParam = searchParams.get("age") || "";
    const bodyPartParam = searchParams.get("body_part") || "全身";

    if (name) setPatientName(name);
    if (genderParam) setGender(genderParam === "男" ? "male" : genderParam === "女" ? "female" : genderParam);
    if (ageParam) setAge(ageParam);
    if (bodyPartParam) setBodyPart(bodyPartParam);
  }, [searchParams]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(UPLOAD_STATE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as Record<string, string>;
      if (data.deviceId) setDeviceId(data.deviceId);
      if (data.deviceModel) setDeviceModel(data.deviceModel);
      if (data.captureTime) setCaptureTime(data.captureTime);
      if (data.patientName) setPatientName(data.patientName);
      if (data.gender) setGender(data.gender);
      if (data.age) setAge(data.age);
      if (data.bodyPart) setBodyPart(data.bodyPart);
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        UPLOAD_STATE_KEY,
        JSON.stringify({
          deviceId,
          deviceModel,
          captureTime,
          patientName,
          gender,
          age,
          bodyPart,
        })
      );
    } catch {
      // ignore storage errors
    }
  }, [deviceId, deviceModel, captureTime, patientName, gender, age, bodyPart]);

  useEffect(() => {
    if (result?.record_id) {
      // 上传完成后，跳转到EMR/诊断分析页面
      router.push(`/emr?record_id=${result.record_id}`);
    }
  }, [result, router]);

  function handlePatientModeChange(mode: "new" | "existing") {
    setPatientMode(mode);
    if (mode === "new") {
      setSelectedPatientId("");
      setPatientName("");
      setGender("");
      setAge("");
    }
  }

  function handleExistingPatientChange(patientId: string) {
    setSelectedPatientId(patientId);
    const patient = patients.find(p => p.patient_id === patientId);
    if (patient) {
      setPatientName(patient.name);
      // 统一转换为 male/female 格式
      const genderValue = patient.gender === "男" ? "male" : patient.gender === "女" ? "female" : patient.gender;
      setGender(genderValue);
      setAge(String(patient.age));
    }
  }

  async function handleUpload() {
    if (files.length === 0) {
      setResult({ error: "请选择至少一个文件" });
      return;
    }

    if (!deviceId.trim()) {
      setResult({ error: "请填写设备ID" });
      return;
    }

    if (!captureTime.trim()) {
      setResult({ error: "请填写采集时间" });
      return;
    }

    if (patientMode === "existing" && !selectedPatientId) {
      setResult({ error: "请选择一个已登记的患者" });
      return;
    }

    setUploading(true);
    setResult(null);
    setUploadProgress(0);
    setUploadStatus("准备上传...");
    setUploadCompleted(false);
    setReportGenerating(false);
    setReportProgress(0);
    setReportStatus("");
    setCurrentStep(0);

    const metadata = {
      device: {
        device_id: deviceId,
        model: deviceModel || undefined,
      },
      capture: {
        capture_time: normalizeCaptureTime(captureTime),
        frame_rate_hz: 9.0,
        resolution: "320x240",
        distance_m: 1.2,
        emissivity: 0.98,
      },
      patient: patientName || gender || age || bodyPart || selectedPatientId ? {
        patient_id: selectedPatientId || undefined,
        name: patientName || undefined,
        gender: gender || undefined,
        age: age ? parseInt(age) : undefined,
        body_part: bodyPart || undefined,
      } : undefined,
    };

    try {
      let record_id: string;

      if (files.length === 1) {
        // Single file — use original /ingest endpoint
        const formData = new FormData();
        formData.append("file", files[0]);
        formData.append("metadata", JSON.stringify(metadata));

        // Use backend direct URL for file uploads to avoid Next proxy body-size limits.
        const response = await uploadFormDataWithProgress(`${API_BACKEND_BASE}/ingest`, formData);
        if (!response.ok) {
          setResult({ error: response.data?.detail || `上传失败（HTTP ${response.status}）` });
          setUploading(false);
          return;
        }
        record_id = response.data.record_id;
      } else {
        // Multiple files — use /ingest/batch, one record + one report for all files
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }
        formData.append("metadata", JSON.stringify(metadata));

        // Use backend direct URL for batch uploads to avoid Next proxy body-size limits.
        const response = await uploadFormDataWithProgress(`${API_BACKEND_BASE}/ingest/batch`, formData);
        if (!response.ok) {
          setResult({ error: response.data?.detail || `批量上传失败（HTTP ${response.status}）` });
          setUploading(false);
          return;
        }
        record_id = response.data.record_id;
      }

      setUploadProgress(100);
      setUploadCompleted(true);
      setUploadStatus("数据上传完成，后台开始分析...");
      setUploading(false);
      setReportGenerating(true);
      setReportStatus(files.length > 1
        ? `${files.length} 个文件上传成功，正在生成合并报告...`
        : "数据上传成功，正在生成报告..."
      );

      await checkReportGeneration(record_id);

      setResult({ record_id });
      flashSuccessButton();
    } catch (error) {
      setResult({ error: `上传失败: ${String(error)}` });
      setUploadStatus("上传失败");
      setUploading(false);
    }
  }

  function checkReportGeneration(recordId: string): Promise<void> {
    return new Promise((resolve) => {
      setReportProgress(10);
      setCurrentStep(1);
      setReportStatus("数据上传完成，后台开始分析...");

      const source = new EventSource(`${API_BACKEND_BASE}/events/ingest-progress/${recordId}`);

      const timeoutId = window.setTimeout(() => {
        source.close();
        setReportProgress(100);
        setReportStatus("分析已在后台进行，稍后可查看报告");
        setReportGenerating(false);
        resolve();
      }, 90_000);

      source.addEventListener("progress", (e: MessageEvent) => {
        try {
          const data = JSON.parse(e.data) as {
            step: number;
            label: string;
            pct: number;
            status: string;
          };
          setReportProgress(data.pct ?? 0);
          setReportStatus(data.label ?? "");
          setCurrentStep(data.step ?? 0);
          if (data.pct >= 100 || data.status === "complete") {
            clearTimeout(timeoutId);
            source.close();
            setReportProgress(100);
            setReportGenerating(false);
            resolve();
          }
        } catch {
          // ignore parse errors
        }
      });

      source.onerror = () => {
        source.close();
        clearTimeout(timeoutId);
        const start = Date.now();
        const poll = setInterval(async () => {
          try {
            const res = await fetch(`${API_BACKEND_BASE}/emr?record_id=${recordId}`);
            if (res.ok) {
              const d = await res.json() as { emr_id?: string };
              if (d?.emr_id) {
                clearInterval(poll);
                setReportProgress(100);
                setReportStatus("报告生成完成！");
                setReportGenerating(false);
                resolve();
                return;
              }
            }
          } catch { /* ignore */ }
          if (Date.now() - start > 90_000) {
            clearInterval(poll);
            setReportProgress(100);
            setReportStatus("分析已在后台进行，稍后可查看报告");
            setReportGenerating(false);
            resolve();
          }
        }, 2000);
      };
    });
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-8 px-6 py-12">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">数据上传</h1>
          <p className="text-slate-600">上传红外热成像数据并生成诊断报告</p>
        </header>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">文件选择</h2>
          <div className="mt-4">
            <label className="block text-sm font-medium text-slate-700">
              数据文件 <span className="text-red-500">*</span>
            </label>
            <div className="mt-2 rounded-lg border-2 border-dashed border-slate-200 hover:border-blue-400 transition-colors p-6 text-center">
              <input
                type="file"
                accept=".csv,.bin,.dat,.npy,.zip,.jpg,.jpeg,.png"
                multiple
                className="hidden"
                id="file-upload"
                onChange={(e) => {
                  const newFiles = Array.from(e.target.files || []);
                  setFiles([...files, ...newFiles]);
                  // 重置 input 以允许重复选择相同文件
                  e.target.value = "";
                }}
              />
              <label htmlFor="file-upload" className="cursor-pointer">
                <div className="text-slate-600">
                  <p className="text-sm font-medium">点击选择文件或拖拽到此处</p>
                  <p className="mt-1 text-xs text-slate-500">支持格式：.csv, .bin, .dat, .npy, .zip（数据）及 .jpg, .png（热成像图片）</p>
                  <p className="mt-1 text-xs text-blue-600 font-medium">同一患者多个文件将合并为一份报告</p>
                </div>
              </label>
            </div>

            {/* 已选择的文件列表 */}
            {files.length > 0 && (
              <div className="mt-4">
                <p className="text-sm font-medium text-slate-700 mb-3">
                  已选择 {files.length} 个文件：
                </p>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {files.map((file, index) => (
                    <div
                      key={`${file.name}-${index}`}
                      className="flex items-center justify-between bg-slate-50 p-3 rounded-lg border border-slate-200 hover:bg-slate-100 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-900 truncate">
                          {file.name}
                        </p>
                        <p className="text-xs text-slate-500">
                          {(file.size / 1024).toFixed(2)} KB
                        </p>
                      </div>
                      <button
                        onClick={() => setFiles(files.filter((_, i) => i !== index))}
                        className="ml-2 px-3 py-1 text-xs font-medium text-red-600 hover:text-red-700 hover:bg-red-50 rounded"
                        title="删除此文件"
                      >
                        删除
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => setFiles([])}
                  className="mt-3 text-xs font-medium text-slate-600 hover:text-slate-700 underline"
                >
                  清空所有
                </button>
              </div>
            )}
          </div>
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">设备信息</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700">
                设备ID <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                placeholder="device-001"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">设备型号</label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={deviceModel}
                onChange={(e) => setDeviceModel(e.target.value)}
              />
            </div>
            <div className="lg:col-span-2">
              <label className="block text-sm font-medium text-slate-700">
                采集时间 <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={captureTime.slice(0, 16)}
                onChange={(e) => setCaptureTime(e.target.value)}
              />
            </div>
          </div>
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">患者信息</h2>
            <div className="flex rounded-lg border border-slate-200 p-1">
              <button
                className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                  patientMode === "new"
                    ? "bg-blue-600 text-white"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                onClick={() => handlePatientModeChange("new")}
              >
                新患者
              </button>
              <button
                className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
                  patientMode === "existing"
                    ? "bg-blue-600 text-white"
                    : "text-slate-600 hover:text-slate-900"
                }`}
                onClick={() => handlePatientModeChange("existing")}
              >
                已有患者
              </button>
            </div>
          </div>

          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            {patientMode === "existing" && (
              <div className="lg:col-span-2">
                <label className="block text-sm font-medium text-slate-700">
                  选择患者 <span className="text-red-500">*</span>
                  {patients.length > 0 && (
                    <span className="ml-2 text-xs text-slate-500">
                      （共 {patients.length} 名已登记患者）
                    </span>
                  )}
                </label>
                {patientsLoading ? (
                  <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
                    {patientsWarming ? "后端服务忙碌，正在等待响应..." : "正在加载患者列表..."}
                  </div>
                ) : patientsError ? (
                  <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    加载失败：{patientsError}
                    <button
                      className="ml-2 text-xs underline"
                      onClick={() => fetchPatients(false)}
                    >
                      重试
                    </button>
                  </div>
                ) : patients.length === 0 ? (
                  <div className="mt-2 rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-2 text-sm text-yellow-700">
                    暂无已登记的患者，请切换到"新患者"模式进行登记
                  </div>
                ) : (
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    value={selectedPatientId}
                    onChange={(e) => handleExistingPatientChange(e.target.value)}
                  >
                    <option value="">请选择已登记的患者</option>
                    {patients.map((patient) => (
                      <option key={patient.patient_id} value={patient.patient_id}>
                        {patient.name} - {formatGender(patient.gender)} - {patient.age}岁
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-slate-700">
                姓名 {patientMode === "new" && <span className="text-slate-400">(可选)</span>}
              </label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:bg-slate-100"
                value={patientName}
                onChange={(e) => setPatientName(e.target.value)}
                disabled={patientMode === "existing"}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">
                性别 {patientMode === "new" && <span className="text-slate-400">(可选)</span>}
              </label>
              <select
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:bg-slate-100"
                value={gender}
                onChange={(e) => setGender(e.target.value)}
                disabled={patientMode === "existing"}
              >
                <option value="">请选择</option>
                <option value="male">男</option>
                <option value="female">女</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">
                年龄 {patientMode === "new" && <span className="text-slate-400">(可选)</span>}
              </label>
              <input
                type="number"
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm disabled:bg-slate-100"
                value={age}
                onChange={(e) => setAge(e.target.value)}
                disabled={patientMode === "existing"}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">
                采集部位 <span className="text-slate-400">(可选)</span>
              </label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={bodyPart}
                onChange={(e) => setBodyPart(e.target.value)}
                placeholder="全身 / 头部 / 颈部 / 肩部"
              />
            </div>
          </div>

          {patientMode === "existing" && selectedPatientId && (
            <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
              已选择患者：{patientName}，将为该患者进行第N次数据采集
            </div>
          )}

          {patientMode === "new" && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
              新患者模式：填写患者信息后系统将自动登记
            </div>
          )}
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <button
            className="w-full rounded-full bg-blue-600 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-slate-300"
            onClick={handleUpload}
            disabled={uploading || reportGenerating || files.length === 0}
          >
            {uploading
              ? `上传中... ${Math.round(uploadProgress)}%`
              : reportGenerating
              ? "生成合并报告中..."
              : files.length > 1
              ? `上传并合并生成报告 (${files.length} 个文件)`
              : files.length === 1
              ? `上传数据 (${files[0].name})`
              : "上传数据"}
          </button>

          {(uploading || uploadCompleted) && (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-semibold text-emerald-900">上传进度</p>
                <p className="text-sm font-semibold text-emerald-700">{Math.round(uploadProgress)}%</p>
              </div>
              <div className="mb-2 h-2 w-full rounded-full bg-emerald-200">
                <div
                  className="h-2 rounded-full bg-emerald-600 transition-all duration-300 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-xs text-emerald-800">{uploadStatus}</p>
              {uploadCompleted && (
                <p className="mt-1 text-xs text-emerald-700">
                  上传完成判定：已收到 record_id，文件已入库，进入分析阶段。
                </p>
              )}
            </div>
          )}

          {reportGenerating && (
            <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-sm font-semibold text-blue-900">分析进度</p>
                <p className="text-sm font-semibold text-blue-700">{Math.round(reportProgress)}%</p>
              </div>
              <div className="mb-3 h-2 w-full rounded-full bg-blue-200">
                <div
                  className="h-2 rounded-full bg-blue-600 transition-all duration-500 ease-out"
                  style={{ width: `${reportProgress}%` }}
                />
              </div>
              <ol className="space-y-1.5">
                {[
                  { step: 1, label: "数据入库" },
                  { step: 2, label: "热成像分析" },
                  { step: 3, label: "电子病历生成" },
                  { step: 4, label: "AI诊断报告" },
                  { step: 5, label: "治疗方案" },
                ].map(({ step, label }) => {
                  const active = currentStep === step;
                  const done = currentStep > step || reportProgress >= 100;
                  return (
                    <li key={step} className="flex items-center gap-2 text-xs">
                      <span
                        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ${
                          done
                            ? "bg-blue-600 text-white"
                            : active
                            ? "animate-pulse bg-blue-400 text-white"
                            : "bg-blue-100 text-blue-400"
                        }`}
                      >
                        {done ? "✓" : step}
                      </span>
                      <span
                        className={
                          done
                            ? "font-medium text-blue-800"
                            : active
                            ? "text-blue-700"
                            : "text-blue-400"
                        }
                      >
                        {label}
                      </span>
                    </li>
                  );
                })}
              </ol>
              <p className="mt-2 text-xs italic text-blue-700">{reportStatus}</p>
            </div>
          )}

          {result && (
            <div className="mt-4">
              {result.error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                  <p className="text-sm font-semibold text-red-900">上传失败</p>
                  <p className="mt-1 text-sm text-red-700">{result.error}</p>
                </div>
              ) : (
                <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                  <p className="text-sm font-semibold text-green-900">上传成功</p>
                  <p className="mt-1 text-xs text-green-600">
                    {files.length > 1
                      ? `已将 ${files.length} 个文件合并为一份报告`
                      : "文件上传成功"}
                  </p>
                  <p className="mt-1 font-mono text-xs text-green-700">
                    Record ID: {result.record_id}
                  </p>
                  <p className="mt-2 text-xs text-green-700">正在跳转到诊断分析...</p>
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default function UploadPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-500">加载中...</div>}>
      <UploadPageContent />
    </Suspense>
  );
}
