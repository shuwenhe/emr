"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { flashSuccessButton } from "../lib/flash";

type Patient = {
  patient_id: string;
  name: string;
  gender: string;
  age: number;
};

const API_BASE = "http://localhost:8000";
const UPLOAD_STATE_KEY = "patient_flow_state_upload";

export default function UploadPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [files, setFiles] = useState<File[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [deviceModel, setDeviceModel] = useState("IR-Thermal-320");
  const [captureTime, setCaptureTime] = useState("");
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
  const [reportGenerating, setReportGenerating] = useState(false);
  const [reportProgress, setReportProgress] = useState(0);
  const [reportStatus, setReportStatus] = useState("");

  useEffect(() => {
    fetchPatients();
  }, []);

  async function fetchPatients() {
    setPatientsLoading(true);
    setPatientsError("");
    try {
      const response = await fetch(`${API_BASE}/patients`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      console.log("Fetched patients:", data);
      setPatients(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error("Failed to fetch patients:", error);
      setPatientsError(String(error));
      setPatients([]);
    } finally {
      setPatientsLoading(false);
    }
  }

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
    if (files.length === 0 || !deviceId || !captureTime) {
      setResult({ error: "请填写必填字段并选择至少一个文件" });
      return;
    }

    if (patientMode === "existing" && !selectedPatientId) {
      setResult({ error: "请选择一个已登记的患者" });
      return;
    }

    setUploading(true);
    setResult(null);
    setReportGenerating(false);
    setReportProgress(0);
    setReportStatus("");

    const metadata = {
      device: {
        device_id: deviceId,
        model: deviceModel || undefined,
      },
      capture: {
        capture_time: captureTime,
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

        const response = await fetch(`${API_BASE}/ingest`, {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (!response.ok) {
          setResult({ error: data.detail || "上传失败" });
          setUploading(false);
          return;
        }
        record_id = data.record_id;
      } else {
        // Multiple files — use /ingest/batch, one record + one report for all files
        const formData = new FormData();
        for (const file of files) {
          formData.append("files", file);
        }
        formData.append("metadata", JSON.stringify(metadata));

        const response = await fetch(`${API_BASE}/ingest/batch`, {
          method: "POST",
          body: formData,
        });
        const data = await response.json();
        if (!response.ok) {
          setResult({ error: data.detail || "批量上传失败" });
          setUploading(false);
          return;
        }
        record_id = data.record_id;
      }

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
      setUploading(false);
    }
  }

  async function checkReportGeneration(recordId: string) {
    const startTime = Date.now();
    const maxWaitTime = 30000; // 最多等待30秒
    const pollInterval = 1000; // 每秒轮询一次
    
    // 模拟进度更新
    const progressInterval = setInterval(() => {
      setReportProgress((prev) => {
        const elapsed = Date.now() - startTime;
        const progress = Math.min(90, (elapsed / maxWaitTime) * 100);
        
        // 根据进度更新状态提示
        if (progress < 20) {
          setReportStatus("正在分析热成像数据...");
        } else if (progress < 50) {
          setReportStatus("正在生成诊断结论...");
        } else if (progress < 80) {
          setReportStatus("正在生成治疗方案...");
        } else {
          setReportStatus("正在生成报告文档...");
        }
        
        return progress;
      });
    }, 100);

    // 轮询检查报告是否生成完成
    while (Date.now() - startTime < maxWaitTime) {
      try {
        const response = await fetch(`${API_BASE}/emr?record_id=${recordId}`);
        if (response.ok) {
          const emrData = await response.json();
          if (emrData && emrData.emr_id) {
            // 报告生成完成
            clearInterval(progressInterval);
            setReportProgress(100);
            setReportStatus("报告生成完成！");
            setReportGenerating(false);
            return;
          }
        }
      } catch {
        // 继续轮询
      }
      
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }
    
    // 超时
    clearInterval(progressInterval);
    setReportProgress(100);
    setReportStatus("报告生成中，请稍后查看...");
    setReportGenerating(false);
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
                value={captureTime}
                onChange={(e) => setCaptureTime(e.target.value + ":00")}
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
                    正在加载患者列表...
                  </div>
                ) : patientsError ? (
                  <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    加载失败：{patientsError}
                    <button
                      className="ml-2 text-xs underline"
                      onClick={() => fetchPatients()}
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
              ? `上传中... (${files.length} 个文件)`
              : reportGenerating
              ? "生成合并报告中..."
              : files.length > 1
              ? `上传并合并生成报告 (${files.length} 个文件)`
              : files.length === 1
              ? `上传数据 (${files[0].name})`
              : "上传数据"}
          </button>

          {reportGenerating && (
            <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
              <div className="flex items-center justify-between mb-2">
                <p className="text-sm font-semibold text-blue-900">报告生成中</p>
                <p className="text-sm font-semibold text-blue-700">{Math.round(reportProgress)}%</p>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-2.5 mb-2">
                <div 
                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-300 ease-out"
                  style={{ width: `${reportProgress}%` }}
                ></div>
              </div>
              <p className="text-xs text-blue-700">{reportStatus}</p>
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
