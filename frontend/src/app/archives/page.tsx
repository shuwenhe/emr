"use client";

import { useEffect, useState } from "react";
import mammoth from "mammoth";

type Patient = {
  patient_id: string;
  name: string | null;
  gender: string | null;
  age: number | null;
  archived: boolean;
  updated_at: string;
};

type ReportFile = {
  date: string;
  name: string;
  size_bytes: number;
  url: string;
  updated_at: number;
};

const API_BASE = "http://localhost:8000";

export default function ArchivesPage() {
  const [archivedPatients, setArchivedPatients] = useState<Patient[]>([]);
  const [archivedReports, setArchivedReports] = useState<ReportFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"patients" | "reports">("patients");
  const [reportPreviewHtml, setReportPreviewHtml] = useState("");
  const [reportPreviewTitle, setReportPreviewTitle] = useState("");
  const [showReportPreview, setShowReportPreview] = useState(false);

  useEffect(() => {
    fetchArchivedPatients();
    fetchArchivedReports();
  }, []);

  async function fetchArchivedPatients() {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/patients?include_archived=true&limit=1000`);
      const data = await response.json();
      const archived = Array.isArray(data) ? data.filter((p: Patient) => p.archived) : [];
      setArchivedPatients(archived);
    } catch (error) {
      console.error("获取归档患者失败:", error);
      setArchivedPatients([]);
    } finally {
      setLoading(false);
    }
  }

  async function fetchArchivedReports() {
    try {
      const response = await fetch(`${API_BASE}/reports/.trash`);
      if (response.ok) {
        const data = await response.json();
        setArchivedReports(Array.isArray(data) ? data : []);
      }
    } catch (error) {
      console.error("获取归档报告失败:", error);
      setArchivedReports([]);
    }
  }

  async function handleRestorePatient(patient: Patient) {
    const confirmed = window.confirm(`确认恢复患者"${patient.name || patient.patient_id}"吗？`);
    if (!confirmed) return;

    try {
      const response = await fetch(
        `${API_BASE}/patients/${encodeURIComponent(patient.patient_id)}/archive`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ archived: false }),
        }
      );

      if (!response.ok) {
        throw new Error("恢复失败");
      }

      alert("恢复成功！");
      fetchArchivedPatients();
    } catch (error) {
      alert(`恢复失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  async function handleRestoreReport(report: ReportFile) {
    const confirmed = window.confirm(`确认恢复报告"${report.name}"吗？`);
    if (!confirmed) return;

    try {
      const response = await fetch(`${API_BASE}/reports/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date: report.date,
          filename: report.name,
          archived: false,
        }),
      });

      if (!response.ok) {
        throw new Error("恢复失败");
      }

      alert("恢复成功！");
      fetchArchivedReports();
    } catch (error) {
      alert(`恢复失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  async function handlePreviewReport(file: ReportFile) {
    const encodedDate = encodeURIComponent(file.date);
    const encodedName = encodeURIComponent(file.name);
    const url = `${API_BASE}/reports/.trash/${encodedDate}/${encodedName}`;

    if (!file.name.toLowerCase().endsWith(".docx")) {
      window.open(url, "_blank", "noopener,noreferrer");
      return;
    }

    try {
      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer });
      setReportPreviewHtml(result.value);
      setReportPreviewTitle(file.name);
      setShowReportPreview(true);
    } catch (error) {
      alert(`预览失败: ${String(error)}`);
    }
  }

  function formatFileSize(bytes: number) {
    if (!bytes || Number.isNaN(bytes)) return "-";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytes;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }
    return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-12">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold text-slate-900">归档管理</h1>
          <p className="mt-2 text-slate-600">查看和恢复已归档的患者与报告</p>
        </header>

        {/* 标签切换 */}
        <div className="mb-6 flex gap-4 border-b border-slate-200">
          <button
            className={`pb-3 text-sm font-medium ${
              activeTab === "patients"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-slate-600 hover:text-slate-900"
            }`}
            onClick={() => setActiveTab("patients")}
          >
            已归档患者 ({archivedPatients.length})
          </button>
          <button
            className={`pb-3 text-sm font-medium ${
              activeTab === "reports"
                ? "border-b-2 border-blue-600 text-blue-600"
                : "text-slate-600 hover:text-slate-900"
            }`}
            onClick={() => setActiveTab("reports")}
          >
            已归档报告 ({archivedReports.length})
          </button>
        </div>

        {/* 患者列表 */}
        {activeTab === "patients" && (
          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            {loading ? (
              <div className="py-12 text-center text-sm text-slate-500">加载中...</div>
            ) : archivedPatients.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-3 font-medium">患者ID</th>
                      <th className="px-4 py-3 font-medium">姓名</th>
                      <th className="px-4 py-3 font-medium">性别</th>
                      <th className="px-4 py-3 font-medium">年龄</th>
                      <th className="px-4 py-3 font-medium">归档时间</th>
                      <th className="px-4 py-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {archivedPatients.map((patient) => (
                      <tr key={patient.patient_id} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono text-xs text-slate-700">
                          {patient.patient_id}
                        </td>
                        <td className="px-4 py-3 font-semibold text-slate-900">
                          {patient.name || "-"}
                        </td>
                        <td className="px-4 py-3 text-slate-700">{patient.gender || "-"}</td>
                        <td className="px-4 py-3 text-slate-700">
                          {patient.age ? `${patient.age}岁` : "-"}
                        </td>
                        <td className="px-4 py-3 text-slate-700">
                          {patient.updated_at
                            ? new Date(patient.updated_at).toLocaleString()
                            : "-"}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            className="rounded-full bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                            onClick={() => handleRestorePatient(patient)}
                          >
                            恢复
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-12 text-center">
                <p className="text-slate-500">暂无归档患者</p>
              </div>
            )}
          </section>
        )}

        {/* 报告列表 */}
        {activeTab === "reports" && (
          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            {archivedReports.length > 0 ? (
              <div className="overflow-hidden rounded-xl border border-slate-200">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-3 font-medium">文件名</th>
                      <th className="px-4 py-3 font-medium">日期</th>
                      <th className="px-4 py-3 font-medium">大小</th>
                      <th className="px-4 py-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {archivedReports.map((file) => (
                      <tr key={`${file.date}-${file.name}`} className="hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-900">{file.name}</td>
                        <td className="px-4 py-3 text-slate-700">{file.date}</td>
                        <td className="px-4 py-3 text-slate-700">
                          {formatFileSize(file.size_bytes)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-2">
                            <button
                              className="rounded-full border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50"
                              onClick={() => handlePreviewReport(file)}
                            >
                              预览
                            </button>
                            <button
                              className="rounded-full bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                              onClick={() => handleRestoreReport(file)}
                            >
                              恢复
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-12 text-center">
                <p className="text-slate-500">暂无归档报告</p>
              </div>
            )}
          </section>
        )}
      </main>

      {/* 报告预览模态框 */}
      {showReportPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative max-h-[90vh] w-full max-w-5xl overflow-auto rounded-2xl bg-white p-8 shadow-xl">
            <div className="mb-6 flex items-center justify-between">
              <h2 className="text-2xl font-semibold text-slate-900">{reportPreviewTitle}</h2>
              <button
                className="rounded-full bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                onClick={() => setShowReportPreview(false)}
              >
                关闭
              </button>
            </div>
            <div
              className="prose max-w-none"
              dangerouslySetInnerHTML={{ __html: reportPreviewHtml }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
