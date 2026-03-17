"use client";

import { useEffect, useState } from "react";
import PDFViewer from "../components/PDFViewer";

type ReportFile = {
  date: string;
  name: string;
  size_bytes: number;
  url: string;
  updated_at: number;
};

const API_BASE = "http://localhost:8000";

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedPdfUrl, setSelectedPdfUrl] = useState<string | null>(null);
  const [selectedPdfTitle, setSelectedPdfTitle] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState("");
  const [filterDate, setFilterDate] = useState<string>("");
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null);

  useEffect(() => {
    fetchReports();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      fetchReports(true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  async function fetchReports(silent = false) {
    if (!silent) {
      setLoading(true);
    }
    try {
      const response = await fetch(`${API_BASE}/reports`);
      if (response.ok) {
        const data = await response.json();
        setReports(Array.isArray(data) ? data : []);
        setLastRefreshedAt(new Date());
      }
    } catch (error) {
      console.error("获取报告失败:", error);
      if (!silent) {
        setReports([]);
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }

  function handlePreviewPdf(report: ReportFile) {
    if (report.name.toLowerCase().endsWith(".pdf")) {
      const encodedDate = encodeURIComponent(report.date);
      const encodedName = encodeURIComponent(report.name);
      const pdfUrl = `${API_BASE}/reports/${encodedDate}/${encodedName}?inline=true`;
      setSelectedPdfUrl(pdfUrl);
      setSelectedPdfTitle(report.name);
    } else {
      // Handle DOCX files
      alert("DOCX 文件预览功能开发中");
    }
  }

  function handleDownload(report: ReportFile) {
    const encodedDate = encodeURIComponent(report.date);
    const encodedName = encodeURIComponent(report.name);
    const downloadUrl = `${API_BASE}/reports/${encodedDate}/${encodedName}`;
    window.open(downloadUrl, "_blank", "noopener,noreferrer");
  }

  function handlePrint(report: ReportFile) {
    if (report.name.toLowerCase().endsWith(".pdf")) {
      const encodedDate = encodeURIComponent(report.date);
      const encodedName = encodeURIComponent(report.name);
      const pdfUrl = `${API_BASE}/reports/${encodedDate}/${encodedName}?inline=true`;
      window.open(pdfUrl, "_blank", "noopener,noreferrer");
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

  function formatDate(timestamp: number) {
    return new Date(timestamp * 1000).toLocaleString("zh-CN");
  }

  // Filter reports
  const filteredReports = reports.filter((report) => {
    const matchesSearch = report.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesDate = !filterDate || report.date === filterDate;
    return matchesSearch && matchesDate;
  });

  // Get unique dates
  const uniqueDates = Array.from(new Set(reports.map((r) => r.date))).sort().reverse();

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-12">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold text-slate-900">历史报告</h1>
          <p className="mt-2 text-slate-600">查看和下载历史报告文件（每5秒自动刷新）</p>
          {lastRefreshedAt && (
            <p className="mt-1 text-xs text-slate-500">
              最近刷新：{lastRefreshedAt.toLocaleTimeString("zh-CN")}
            </p>
          )}
        </header>

        {/* 搜索和过滤 */}
        <div className="mb-6 flex flex-col gap-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 md:flex-row">
          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-2">
              搜索报告名称
            </label>
            <input
              type="text"
              placeholder="输入报告名称..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              按日期筛选
            </label>
            <select
              value={filterDate}
              onChange={(e) => setFilterDate(e.target.value)}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none"
            >
              <option value="">所有日期</option>
              {uniqueDates.map((date) => (
                <option key={date} value={date}>
                  {date}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* 报告列表 */}
        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          {loading ? (
            <div className="py-12 text-center text-sm text-slate-500">加载中...</div>
          ) : filteredReports.length > 0 ? (
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-4 py-3 font-medium">报告名称</th>
                    <th className="px-4 py-3 font-medium">日期</th>
                    <th className="px-4 py-3 font-medium">文件大小</th>
                    <th className="px-4 py-3 font-medium">修改时间</th>
                    <th className="px-4 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {filteredReports.map((report) => (
                    <tr key={`${report.date}-${report.name}`} className="hover:bg-slate-50">
                      <td className="px-4 py-3 text-slate-900 font-medium truncate max-w-xs">
                        <span title={report.name}>{report.name}</span>
                      </td>
                      <td className="px-4 py-3 text-slate-600">{report.date}</td>
                      <td className="px-4 py-3 text-slate-600">{formatFileSize(report.size_bytes)}</td>
                      <td className="px-4 py-3 text-slate-600 text-sm">
                        {formatDate(report.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          {report.name.toLowerCase().endsWith(".pdf") && (
                            <button
                              onClick={() => handlePreviewPdf(report)}
                              className="text-xs font-semibold text-blue-600 hover:text-blue-700 hover:underline"
                              title="在线预览"
                            >
                              查看
                            </button>
                          )}
                          <button
                            onClick={() => handleDownload(report)}
                            className="text-xs font-semibold text-blue-600 hover:text-blue-700 hover:underline"
                            title="下载文件"
                          >
                            下载
                          </button>
                          {report.name.toLowerCase().endsWith(".pdf") && (
                            <button
                              onClick={() => handlePrint(report)}
                              className="text-xs font-semibold text-blue-600 hover:text-blue-700 hover:underline"
                              title="打印"
                            >
                              打印
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="py-12 text-center text-slate-500">
              {reports.length === 0 ? "没有报告文件" : "没有匹配的报告"}
            </div>
          )}
        </section>

        {/* 统计信息 */}
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <p className="text-sm font-medium text-slate-600">总报告数</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{reports.length}</p>
          </div>
          <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <p className="text-sm font-medium text-slate-600">PDF 文件</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">
              {reports.filter((r) => r.name.toLowerCase().endsWith(".pdf")).length}
            </p>
          </div>
          <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <p className="text-sm font-medium text-slate-600">总大小</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">
              {formatFileSize(reports.reduce((sum, r) => sum + r.size_bytes, 0))}
            </p>
          </div>
          <div className="rounded-xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
            <p className="text-sm font-medium text-slate-600">独立日期</p>
            <p className="mt-1 text-2xl font-semibold text-slate-900">{uniqueDates.length}</p>
          </div>
        </div>
      </main>

      {/* PDF 查看器 */}
      {selectedPdfUrl && (
        <PDFViewer
          pdfUrl={selectedPdfUrl}
          title={selectedPdfTitle}
          onClose={() => setSelectedPdfUrl(null)}
        />
      )}
    </div>
  );
}
