"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import mammoth from "mammoth";

type EmrResponse = Record<string, unknown> | Array<Record<string, unknown>>;
type ReportPayload = Record<string, unknown> | null;
type ReportFile = {
  date: string;
  name: string;
  size_bytes: number;
  url: string;
  updated_at: number;
};

const API_BASE = "http://localhost:8000";
const EMR_STATE_KEY = "patient_flow_state_emr";

export default function EmrPage() {
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
  const [output, setOutput] = useState<EmrResponse | { error: string }>({
    error: "请先执行操作",
  });

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
    return "";
  }, [report]);
  const visibleReportFiles = useMemo(() => {
    if (!currentPatientName) {
      return [] as ReportFile[];
    }
    const prefix = `${currentPatientName}_`;
    return reportFiles.filter((file) => file.name.startsWith(prefix));
  }, [currentPatientName, reportFiles]);

  const fetchReports = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/reports`);
      const data = (await response.json()) as ReportFile[];
      setReportFiles(Array.isArray(data) ? data : []);
    } catch {
      setReportFiles([]);
    }
  }, []);

  useEffect(() => {
    fetchReports();
  }, [fetchReports]);

  useEffect(() => {
    const recordIdParam = searchParams.get("record_id") || "";
    if (recordIdParam) {
      setRecordId(recordIdParam);
    }
  }, [searchParams]);

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

  async function handleGenerate() {
    if (!recordId.trim()) {
      setOutput({ error: "record_id 不能为空" });
      return;
    }
    const data = await postJson(`${API_BASE}/emr/generate`, {
      record_id: recordId.trim(),
    });
    setOutput(data as EmrResponse);
    syncEmrFields(data as EmrResponse);
    setReport(extractReport(data as EmrResponse));
    fetchReports();
  }

  async function handleFetch() {
    if (!emrId.trim()) {
      setOutput({ error: "emr_id 不能为空" });
      return;
    }
    const response = await fetch(`${API_BASE}/emr/${emrId.trim()}`);
    const data = (await response.json()) as EmrResponse;
    setOutput(data);
    syncEmrFields(data);
    setReport(extractReport(data));
  }

  async function handleList() {
    const query = patientId.trim()
      ? `?patient_id=${encodeURIComponent(patientId.trim())}`
      : "";
    const response = await fetch(`${API_BASE}/emr${query}`);
    const data = (await response.json()) as EmrResponse;
    setOutput(data);
    setReport(extractReport(data));
  }

  async function handleSave() {
    if (!emrId.trim()) {
      setOutput({ error: "请先获取病历" });
      return;
    }
    const data = await putJson(`${API_BASE}/emr/${emrId.trim()}`, {
      diagnosis,
      doctor_opinion: doctorOpinion,
    });
    setOutput(data as EmrResponse);
    syncEmrFields(data as EmrResponse);
    setReport(extractReport(data as EmrResponse));
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
            <div class="card"><div class="label">性别/年龄</div><div class="value">${String(patient.gender || "-")} / ${String(patient.age || "-")}</div></div>
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

    const printWindow = window.open("", "_blank", "width=800,height=900");
    if (!printWindow) {
      setOutput({ error: "无法打开打印窗口" });
      return;
    }
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  }

  function handlePrint() {
    window.print();
  }

  async function handleViewDocx(url: string) {
    try {
      const response = await fetch(`${API_BASE}${url}`);
      const arrayBuffer = await response.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer });
      setPreviewHtml(result.value);
      setShowPreview(true);
    } catch (error) {
      setOutput({ error: `预览失败: ${String(error)}` });
    }
  }

  async function handlePrintDocx(url: string) {
    try {
      const response = await fetch(`${API_BASE}${url}`);
      const arrayBuffer = await response.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer });
      const printWindow = window.open("", "_blank", "width=900,height=1000");
      if (!printWindow) {
        setOutput({ error: "无法打开打印窗口" });
        return;
      }
      printWindow.document.open();
      printWindow.document.write(`
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
      printWindow.document.close();
      printWindow.focus();
      printWindow.print();
    } catch (error) {
      setOutput({ error: `打印失败: ${String(error)}` });
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="flex min-h-screen w-full flex-col gap-8 px-10 py-12">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">电子病历管理</h1>
          <p className="text-slate-600">
            自动生成、存储与调取病历，并与诊断报告联动。
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-3">
          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
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
              className="mt-4 w-full rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              onClick={handleGenerate}
            >
              生成诊断报告
            </button>
            <p className="mt-3 text-xs text-slate-500">
              将基于采集数据自动生成诊断报告
            </p>
          </div>

          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
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
              className="mt-4 w-full rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
              onClick={handleFetch}
            >
              获取病历
            </button>
          </div>

          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
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
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">结果</h2>
          <pre className="mt-4 max-h-[220px] overflow-y-auto whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-xs text-slate-100">
            {outputText}
          </pre>
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-slate-900">诊断报告</h2>
            <button
              className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              onClick={handleExportReportJson}
            >
              导出报告（JSON）
            </button>
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
                {report.analysis && typeof report.analysis === "object" && (
                  <div className="rounded-xl border border-slate-200 bg-blue-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-blue-600">风险等级</p>
                    <p className="mt-1 text-lg font-bold uppercase text-blue-900">
                      {String((report.analysis as Record<string, unknown>).risk_level ?? "-")}
                    </p>
                  </div>
                )}
              </div>

              {report.analysis && typeof report.analysis === "object" && (report.analysis as Record<string, unknown>).temperature_metrics && (
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

              {report.analysis && typeof report.analysis === "object" && 
               (report.analysis as Record<string, unknown>).regional_comparison && 
               typeof (report.analysis as Record<string, unknown>).regional_comparison === "object" &&
               ((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions &&
               Array.isArray(((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions) &&
               (((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions as unknown[]).length > 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <h3 className="text-sm font-semibold text-amber-900">异常区域</h3>
                  <div className="mt-3 space-y-2">
                    {(((report.analysis as Record<string, unknown>).regional_comparison as Record<string, unknown>).abnormal_regions as Record<string, unknown>[]).map((region, idx) => (
                      <div key={idx} className="flex items-center justify-between rounded-lg bg-white p-3">
                        <span className="font-mono text-sm text-slate-700">{String(region.region)}</span>
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

        {report && report.thermal_marked_image && (
          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">热成像图</h2>
            <div className="mt-4">
              <img
                src={`${API_BASE}/${String(report.thermal_marked_image)}`}
                alt="Thermal Marked Image"
                className="w-full max-w-2xl rounded-xl border border-slate-200"
              />
            </div>
          </section>
        )}

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">历史报告文件</h2>
          {currentPatientName ? (
            visibleReportFiles.length ? (
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
                  {visibleReportFiles.map((file) => (
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
                            href={`${API_BASE}${file.url}`}
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
          ) : (
            <p className="mt-4 text-sm text-slate-500">该患者暂无报告文件</p>
          )
          ) : (
            <p className="mt-4 text-sm text-slate-500">请先生成诊断报告以查看患者历史报告</p>
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
                onClick={() => setShowPreview(false)}
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
      </main>
    </div>
  );
}
