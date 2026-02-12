"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import mammoth from "mammoth";
import { flashSuccessButton } from "../lib/flash";

type Patient = {
  patient_id: string;
  name: string | null;
  gender: string | null;
  age: number | null;
  id_card?: string;
  phone?: string;
  address?: string;
  emergency_contact?: string;
  emergency_phone?: string;
  allergies?: string;
  medical_history?: string;
  department?: string;
  chief_complaint?: string;
  updated_at: string;
};

type EmrRecord = {
  emr_id: string;
  record_id: string;
  created_at: string;
  diagnosis: string | null;
  archived: boolean;
};

type ReportFile = {
  date: string;
  name: string;
  size_bytes: number;
  url: string;
  updated_at: number;
};

type NewPatient = {
  name: string;
  gender: string;
  birth_date: string;
  id_card: string;
  phone: string;
  address: string;
  emergency_contact: string;
  emergency_phone: string;
  allergies: string;
  medical_history: string;
  department: string;
  chief_complaint: string;
};

const API_BASE = "http://localhost:8000";
const PATIENTS_STATE_KEY = "patient_flow_state_patients";
const PATIENT_FLOW_KEYS = [
  "patient_flow_state_patients",
  "patient_flow_state_upload",
  "patient_flow_state_emr",
  "patient_flow_state_treatment",
  "last_emr_context",
];

export default function PatientsPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [emrs, setEmrs] = useState<EmrRecord[]>([]);
  const [reportFiles, setReportFiles] = useState<ReportFile[]>([]);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportPatient, setReportPatient] = useState<Patient | null>(null);
  const [reportPreviewHtml, setReportPreviewHtml] = useState("");
  const [reportPreviewTitle, setReportPreviewTitle] = useState("");
  const [showReportPreview, setShowReportPreview] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [showRegisterForm, setShowRegisterForm] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [reportDateFrom, setReportDateFrom] = useState("");
  const [reportDateTo, setReportDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<NewPatient>({
    name: "",
    gender: "男",
    birth_date: "",
    id_card: "",
    phone: "",
    address: "",
    emergency_contact: "",
    emergency_phone: "",
    allergies: "",
    medical_history: "",
    department: "中医科",
    chief_complaint: ""
  });
  const [birthYear, setBirthYear] = useState("");
  const [birthMonth, setBirthMonth] = useState("");
  const [birthDay, setBirthDay] = useState("");
  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 100 }, (_, i) => String(currentYear - i));
  const months = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, "0"));

  const getDaysInMonth = (year: string, month: string) => {
    if (!year || !month) return [] as string[];
    const days = new Date(Number(year), Number(month), 0).getDate();
    return Array.from({ length: days }, (_, i) => String(i + 1).padStart(2, "0"));
  };

  const updateBirthDate = (year: string, month: string, day: string) => {
    if (year && month && day) {
      setFormData((prev) => ({ ...prev, birth_date: `${year}-${month}-${day}` }));
    } else {
      setFormData((prev) => ({ ...prev, birth_date: "" }));
    }
  };

  useEffect(() => {
    fetchPatients(1, true);
  }, []);

  // 无限滚动监听
  useEffect(() => {
    const handleScroll = () => {
      if (loading || !hasMore) return;
      
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      const scrollHeight = document.documentElement.scrollHeight;
      const clientHeight = document.documentElement.clientHeight;
      
      // 当滚动到距离底部200px时触发加载
      if (scrollTop + clientHeight >= scrollHeight - 200) {
        loadMore();
      }
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, [loading, hasMore, page]);

  function savePatientsState(partial: Record<string, unknown>) {
    try {
      const raw = localStorage.getItem(PATIENTS_STATE_KEY);
      const data = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      localStorage.setItem(PATIENTS_STATE_KEY, JSON.stringify({ ...data, ...partial }));
    } catch {
      // ignore storage errors
    }
  }

  function persistCurrentPatient(patient: Patient) {
    savePatientsState({
      currentPatientId: patient.patient_id,
      currentPatient: {
        patient_id: patient.patient_id,
        name: patient.name ?? "",
        gender: patient.gender ?? "",
        age: patient.age ?? null,
      },
    });
  }

  useEffect(() => {
    try {
      const raw = localStorage.getItem(PATIENTS_STATE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as Record<string, string>;
      if (data.searchQuery) setSearchQuery(data.searchQuery);
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      try {
        savePatientsState({ searchQuery });
      } catch {
        // ignore storage errors
      }
    }, 500);
    return () => clearTimeout(timeoutId);
  }, [searchQuery]);

  function clearPatientFlowState() {
    try {
      PATIENT_FLOW_KEYS.forEach((key) => localStorage.removeItem(key));
    } catch {
      // ignore storage errors
    }
  }

  function normalizeGender(gender: string | null | undefined): string {
    if (!gender) return "";
    const g = String(gender).toLowerCase().trim();
    if (g === "male" || g === "男" || g === "m") return "male";
    if (g === "female" || g === "女" || g === "f") return "female";
    return g;
  }

  function createPatientSignature(name: string | null | undefined, gender: string | null | undefined, age: number | null | undefined): string {
    const normalizedGender = normalizeGender(gender);
    return `${String(name ?? "").trim()}|${normalizedGender}|${age ?? ""}`.toLowerCase();
  }

  async function loadMore() {
    if (loading || !hasMore) return;
    const nextPage = page + 1;
    await fetchPatients(nextPage, false);
  }

  async function fetchPatients(pageNum: number = 1, reset: boolean = false) {
    if (loading) return;
    setLoading(true);
    try {
      if (reset || pageNum === 1) {
        // 只获取已注册的患者，不从EMR补充
        const allPatientsResponse = await fetch(`${API_BASE}/patients?page=1&limit=10000`);
        const allRegisteredPatients = await allPatientsResponse.json();
        
        if (Array.isArray(allRegisteredPatients)) {
          setPatients(allRegisteredPatients);
        } else {
          setPatients([]);
        }
        
        setPage(1);
        setHasMore(false);
      }
    } catch (error) {
      console.error("获取患者列表失败:", error);
      if (reset) {
        setPatients([]);
      }
    } finally {
      setLoading(false);
    }
  }

  async function fetchPatientEmrs(patient: Patient) {
    try {
      const response = await fetch(`${API_BASE}/emr?patient_id=${encodeURIComponent(patient.patient_id)}`);
      const data = await response.json();
      setEmrs(Array.isArray(data) ? data : []);
      setSelectedPatient(patient);
      setShowDetailModal(true);
      if (response.ok) {
        flashSuccessButton();
      }
    } catch {
      setEmrs([]);
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

  function filterReportsForPatient(files: ReportFile[], patient: Patient | null) {
    if (!patient) return [] as ReportFile[];
    const name = patient.name?.trim();
    const id = patient.patient_id?.trim();
    
    return files.filter((file) => {
      if (!file.name) return false;
      const lower = file.name.toLowerCase();
      
      // 按患者名字或ID过滤
      const matchPatient = (name && file.name.startsWith(`${name}_`)) ||
                          (name && lower.includes(name.toLowerCase())) ||
                          (id && lower.includes(id.toLowerCase()));
      if (!matchPatient) return false;
      
      // 按日期范围过滤
      if (reportDateFrom || reportDateTo) {
        const fileDate = new Date(file.date);
        if (reportDateFrom) {
          const fromDate = new Date(reportDateFrom);
          if (fileDate < fromDate) return false;
        }
        if (reportDateTo) {
          const toDate = new Date(reportDateTo);
          // 包含结束日期的整个一天
          toDate.setDate(toDate.getDate() + 1);
          if (fileDate >= toDate) return false;
        }
      }
      
      return true;
    });
  }

  function buildReportFileUrl(file: ReportFile) {
    const encodedDate = encodeURIComponent(file.date);
    const encodedName = encodeURIComponent(file.name);
    return `${API_BASE}/reports/preview?date=${encodedDate}&filename=${encodedName}`;
  }

  function buildReportDownloadUrl(file: ReportFile) {
    const encodedDate = encodeURIComponent(file.date);
    const encodedName = encodeURIComponent(file.name);
    return `${API_BASE}/reports/${encodedDate}/${encodedName}`;
  }

  async function handleOpenReportHistory(patient: Patient) {
    setReportLoading(true);
    setReportError(null);
    setReportPatient(patient);
    setShowReportModal(true);
    // 重置日期范围
    setReportDateFrom("");
    setReportDateTo("");
    try {
      const response = await fetch(`${API_BASE}/reports`);
      const data = await response.json();
      const files = Array.isArray(data) ? (data as ReportFile[]) : [];
      setReportFiles(filterReportsForPatient(files, patient));
      if (response.ok) {
        flashSuccessButton();
      }
    } catch {
      setReportFiles([]);
      setReportError("获取报告列表失败");
    } finally {
      setReportLoading(false);
    }
  }

  function handleReportDateFilterChange() {
    if (reportPatient) {
      setReportFiles(filterReportsForPatient(reportFiles, reportPatient));
      flashSuccessButton();
    }
  }

  async function handlePreviewReport(file: ReportFile) {
    setReportError(null);
    const url = buildReportFileUrl(file);
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
      flashSuccessButton();
    } catch (error) {
      setReportError(`预览失败: ${String(error)}`);
    }
  }

  async function handlePrintReport(file: ReportFile) {
    setReportError(null);
    const url = buildReportFileUrl(file);
    if (!file.name.toLowerCase().endsWith(".docx")) {
      window.open(url, "_blank", "noopener,noreferrer");
      return;
    }
    try {
      const response = await fetch(url);
      const arrayBuffer = await response.arrayBuffer();
      const result = await mammoth.convertToHtml({ arrayBuffer });
      const printWindow = window.open("", "_blank", "width=900,height=1000");
      if (!printWindow) {
        setReportError("无法打开打印窗口");
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
      flashSuccessButton();
    } catch (error) {
      setReportError(`打印失败: ${String(error)}`);
    }
  }

  async function handleArchiveReport(file: ReportFile) {
    const confirmed = window.confirm(`确认将报告“${file.name}”移入回收站吗？`);
    if (!confirmed) return;
    setReportError(null);
    try {
      const response = await fetch(`${API_BASE}/reports/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ date: file.date, filename: file.name, archived: true }),
      });
      if (!response.ok) {
        throw new Error("报告归档失败");
      }
      if (reportPatient) {
        const refresh = await fetch(`${API_BASE}/reports`).then((r) => r.json());
        const files = Array.isArray(refresh) ? (refresh as ReportFile[]) : [];
        setReportFiles(filterReportsForPatient(files, reportPatient));
      } else {
        setReportFiles((prev) => prev.filter((item) => item !== file));
      }
      flashSuccessButton();
    } catch (error) {
      setReportError(`归档失败: ${String(error)}`);
    }
  }

  async function handleArchivePatient(patient: Patient) {
    const confirmed = window.confirm(`确认归档患者“${patient.name || patient.patient_id}”吗？`);
    if (!confirmed) return;
    try {
      const response = await fetch(`${API_BASE}/patients/${encodeURIComponent(patient.patient_id)}/archive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ archived: true }),
      });
      if (!response.ok) {
        throw new Error("归档失败");
      }
      setPatients((prev) => prev.filter((item) => item.patient_id !== patient.patient_id));
      if (selectedPatient?.patient_id === patient.patient_id) {
        setSelectedPatient(null);
        setShowDetailModal(false);
      }
      flashSuccessButton();
    } catch (error) {
      alert(`归档失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  async function handleRegisterPatient(e: React.FormEvent) {
    e.preventDefault();
    
    try {
      // 构造患者数据
      const patientData = {
        name: formData.name,
        gender: formData.gender,
        birth_date: formData.birth_date,
        id_card: formData.id_card,
        phone: formData.phone,
        address: formData.address,
        emergency_contact: formData.emergency_contact,
        emergency_phone: formData.emergency_phone,
        allergies: formData.allergies,
        medical_history: formData.medical_history,
        department: formData.department,
        chief_complaint: formData.chief_complaint
      };
      
      // 调用后端API注册患者
      const response = await fetch(`${API_BASE}/patients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patientData)
      });
      
      if (!response.ok) {
        throw new Error("注册失败");
      }
      
      const result = await response.json();
      
      // 关闭表单并刷新患者列表
      setShowRegisterForm(false);
      setHasMore(true);
      await fetchPatients(1, true);
      
      // 重置表单
      setFormData({
        name: "",
        gender: "男",
        birth_date: "",
        id_card: "",
        phone: "",
        address: "",
        emergency_contact: "",
        emergency_phone: "",
        allergies: "",
        medical_history: "",
        department: "中医科",
        chief_complaint: ""
      });
      setBirthYear("");
      setBirthMonth("");
      setBirthDay("");
      
      alert(`患者注册成功！患者ID: ${result.patient_id}`);
      flashSuccessButton();
      const params = new URLSearchParams({
        name: formData.name,
        gender: formData.gender,
        age: formData.birth_date
          ? String(new Date().getFullYear() - new Date(formData.birth_date).getFullYear())
          : "",
        body_part: "全身",
      });
      router.push(`/upload?${params.toString()}`);
    } catch (error) {
      alert(`注册失败: ${error instanceof Error ? error.message : "未知错误"}`);
    }
  }

  function handleInputChange(field: keyof NewPatient, value: string) {
    setFormData(prev => ({ ...prev, [field]: value }));
  }

  const filteredPatients = patients.filter((p) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      (p.patient_id && p.patient_id.toLowerCase().includes(query)) ||
      (p.name && p.name.toLowerCase().includes(query)) ||
      (p.id_card && p.id_card.toLowerCase().includes(query)) ||
      (p.phone && p.phone.includes(query))
    );
  });

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-12">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-slate-900">患者登记</h1>
            <p className="mt-2 text-slate-600">患者信息登记与管理</p>
          </div>
          <button
            className="rounded-full bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
            onClick={() => {
              clearPatientFlowState();
              setShowRegisterForm(true);
              flashSuccessButton();
            }}
          >
            + 新增患者
          </button>
        </header>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="mb-6">
            <input
              className="w-full max-w-md rounded-lg border border-slate-200 px-4 py-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
              placeholder="搜索患者ID、姓名、身份证号或手机号..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {filteredPatients.length > 0 ? (
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="px-4 py-3 font-medium">患者ID</th>
                    <th className="px-4 py-3 font-medium">姓名</th>
                    <th className="px-4 py-3 font-medium">性别</th>
                    <th className="px-4 py-3 font-medium">年龄</th>
                    <th className="px-4 py-3 font-medium">登记时间</th>
                    <th className="px-4 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {filteredPatients.map((patient) => (
                    <tr key={patient.patient_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-mono text-xs text-slate-700">
                        {patient.patient_id}
                      </td>
                      <td className="px-4 py-3 font-semibold text-slate-900">
                        {patient.name || "-"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {patient.gender || "-"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {patient.age ? `${patient.age}岁` : "-"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {patient.updated_at ? new Date(patient.updated_at).toLocaleDateString() : "-"}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <button
                            className="rounded-full border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50"
                            onClick={() => {
                              persistCurrentPatient(patient);
                              fetchPatientEmrs(patient);
                            }}
                          >
                            病历
                          </button>
                          <button
                            className="rounded-full border border-green-200 px-3 py-1 text-xs font-semibold text-green-600 hover:bg-green-50"
                            onClick={() => {
                              persistCurrentPatient(patient);
                              handleOpenReportHistory(patient);
                            }}
                          >
                            报告
                          </button>
                          <button
                            className="rounded-full border border-rose-200 px-3 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-50"
                            onClick={() => handleArchivePatient(patient)}
                          >
                            归档
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
              <p className="text-slate-500">暂无患者数据</p>
              <button
                className="mt-4 text-sm text-blue-600 hover:text-blue-700"
                onClick={() => {
                  clearPatientFlowState();
                  setShowRegisterForm(true);
                  flashSuccessButton();
                }}
              >
                立即登记患者
              </button>
            </div>
          )}
          
          {/* 加载更多指示器 */}
          {loading && (
            <div className="py-8 text-center">
              <div className="inline-flex items-center space-x-2 text-sm text-slate-500">
                <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <span>加载中...</span>
              </div>
            </div>
          )}
          
          {/* 已加载全部数据提示 */}
          {!hasMore && patients.length > 0 && (
            <div className="py-8 text-center text-sm text-slate-400">
              已显示全部患者数据
            </div>
          )}
        </section>

        {/* 患者登记表单模态框 */}
        {showRegisterForm && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="relative max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl bg-white p-8 shadow-xl">
              <div className="mb-6 flex items-center justify-between">
                <h2 className="text-2xl font-semibold text-slate-900">患者信息登记</h2>
                <button
                  className="rounded-full bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                  onClick={() => {
                    setShowRegisterForm(false);
                    flashSuccessButton();
                  }}
                >
                  取消
                </button>
              </div>

              <form onSubmit={handleRegisterPatient} className="space-y-6">
                {/* 基本信息 */}
                <div className="rounded-xl border border-slate-200 p-6">
                  <h3 className="mb-4 text-lg font-semibold text-slate-900">基本信息</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">
                        姓名 <span className="text-red-500">*</span>
                      </label>
                      <input
                        required
                        type="text"
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.name}
                        onChange={(e) => handleInputChange("name", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">
                        性别 <span className="text-red-500">*</span>
                      </label>
                      <select
                        required
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.gender}
                        onChange={(e) => handleInputChange("gender", e.target.value)}
                      >
                        <option value="男">男</option>
                        <option value="女">女</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">
                        出生日期 <span className="text-red-500">*</span>
                      </label>
                      <div className="mt-2 grid grid-cols-3 gap-2">
                        <select
                          required
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          value={birthYear}
                          onChange={(e) => {
                            const value = e.target.value;
                            setBirthYear(value);
                            updateBirthDate(value, birthMonth, birthDay);
                          }}
                        >
                          <option value="">年</option>
                          {years.map((y) => (
                            <option key={y} value={y}>{y}</option>
                          ))}
                        </select>
                        <select
                          required
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          value={birthMonth}
                          onChange={(e) => {
                            const value = e.target.value;
                            setBirthMonth(value);
                            updateBirthDate(birthYear, value, birthDay);
                          }}
                        >
                          <option value="">月</option>
                          {months.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                        <select
                          required
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                          value={birthDay}
                          onChange={(e) => {
                            const value = e.target.value;
                            setBirthDay(value);
                            updateBirthDate(birthYear, birthMonth, value);
                          }}
                        >
                          <option value="">日</option>
                          {getDaysInMonth(birthYear, birthMonth).map((d) => (
                            <option key={d} value={d}>{d}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">
                        身份证号 <span className="text-red-500">*</span>
                      </label>
                      <input
                        required
                        type="text"
                        maxLength={18}
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.id_card}
                        onChange={(e) => handleInputChange("id_card", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">
                        联系电话 <span className="text-red-500">*</span>
                      </label>
                      <input
                        required
                        type="tel"
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.phone}
                        onChange={(e) => handleInputChange("phone", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">
                        就诊科室
                      </label>
                      <select
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.department}
                        onChange={(e) => handleInputChange("department", e.target.value)}
                      >
                        <option value="中医科">中医科</option>
                        <option value="针灸科">针灸科</option>
                        <option value="推拿科">推拿科</option>
                        <option value="康复科">康复科</option>
                        <option value="内科">内科</option>
                        <option value="外科">外科</option>
                      </select>
                    </div>
                  </div>
                  <div className="mt-4">
                    <label className="block text-sm font-medium text-slate-700">联系地址</label>
                    <input
                      type="text"
                      className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      value={formData.address}
                      onChange={(e) => handleInputChange("address", e.target.value)}
                    />
                  </div>
                </div>

                {/* 紧急联系人 */}
                <div className="rounded-xl border border-slate-200 p-6">
                  <h3 className="mb-4 text-lg font-semibold text-slate-900">紧急联系人</h3>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">联系人姓名</label>
                      <input
                        type="text"
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.emergency_contact}
                        onChange={(e) => handleInputChange("emergency_contact", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">联系人电话</label>
                      <input
                        type="tel"
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        value={formData.emergency_phone}
                        onChange={(e) => handleInputChange("emergency_phone", e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                {/* 医疗信息 */}
                <div className="rounded-xl border border-slate-200 p-6">
                  <h3 className="mb-4 text-lg font-semibold text-slate-900">医疗信息</h3>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">主诉症状</label>
                      <textarea
                        rows={3}
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        placeholder="请描述患者主要症状..."
                        value={formData.chief_complaint}
                        onChange={(e) => handleInputChange("chief_complaint", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">过敏史</label>
                      <textarea
                        rows={2}
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        placeholder="如：青霉素过敏、花粉过敏等"
                        value={formData.allergies}
                        onChange={(e) => handleInputChange("allergies", e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">既往病史</label>
                      <textarea
                        rows={2}
                        className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                        placeholder="如：高血压、糖尿病等"
                        value={formData.medical_history}
                        onChange={(e) => handleInputChange("medical_history", e.target.value)}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end gap-3">
                  <button
                    type="button"
                    className="rounded-full border border-slate-200 px-6 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                    onClick={() => {
                      setShowRegisterForm(false);
                      flashSuccessButton();
                    }}
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    className="rounded-full bg-blue-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-blue-700"
                  >
                    提交登记
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* 患者详情模态框 */}
        {showDetailModal && selectedPatient && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="relative max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl bg-white p-8 shadow-xl">
              <div className="mb-6 flex items-center justify-between">
                <h2 className="text-2xl font-semibold text-slate-900">患者详细信息</h2>
                <button
                  className="rounded-full bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                  onClick={() => {
                    setShowDetailModal(false);
                    flashSuccessButton();
                  }}
                >
                  关闭
                </button>
              </div>

              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">患者ID</p>
                    <p className="mt-1 font-mono text-sm text-slate-900">{selectedPatient.patient_id}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">姓名</p>
                    <p className="mt-1 text-lg font-semibold text-slate-900">{selectedPatient.name || "-"}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">性别</p>
                    <p className="mt-1 text-sm text-slate-900">{selectedPatient.gender || "-"}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">年龄</p>
                    <p className="mt-1 text-sm text-slate-900">{selectedPatient.age ? `${selectedPatient.age}岁` : "-"}</p>
                  </div>
                  {selectedPatient.phone && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">联系电话</p>
                      <p className="mt-1 text-sm text-slate-900">{selectedPatient.phone}</p>
                    </div>
                  )}
                  {selectedPatient.department && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">就诊科室</p>
                      <p className="mt-1 text-sm text-slate-900">{selectedPatient.department}</p>
                    </div>
                  )}
                </div>

                {selectedPatient.address && (
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">联系地址</p>
                    <p className="mt-2 text-sm text-slate-900">{selectedPatient.address}</p>
                  </div>
                )}

                {(selectedPatient.allergies || selectedPatient.medical_history || selectedPatient.chief_complaint) && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                    <h3 className="text-sm font-semibold text-amber-900">医疗信息</h3>
                    {selectedPatient.chief_complaint && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-amber-700">主诉症状</p>
                        <p className="mt-1 text-sm text-amber-900">{selectedPatient.chief_complaint}</p>
                      </div>
                    )}
                    {selectedPatient.allergies && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-amber-700">过敏史</p>
                        <p className="mt-1 text-sm text-amber-900">{selectedPatient.allergies}</p>
                      </div>
                    )}
                    {selectedPatient.medical_history && (
                      <div className="mt-3">
                        <p className="text-xs font-medium text-amber-700">既往病史</p>
                        <p className="mt-1 text-sm text-amber-900">{selectedPatient.medical_history}</p>
                      </div>
                    )}
                  </div>
                )}

                {emrs.length > 0 && (
                  <div className="rounded-xl border border-slate-200 p-4">
                    <h3 className="text-sm font-semibold text-slate-900">病历记录</h3>
                    <div className="mt-3 space-y-2">
                      {emrs.map((emr) => (
                        <Link
                          key={emr.emr_id}
                          href={`/emr?id=${emr.emr_id}`}
                          className="flex items-center justify-between rounded-lg border border-slate-200 p-3 hover:bg-slate-50"
                        >
                          <div>
                            <p className="text-sm font-medium text-slate-900">
                              {emr.diagnosis || "待诊断"}
                            </p>
                            <p className="text-xs text-slate-500">{emr.created_at}</p>
                          </div>
                          <span className="text-xs text-blue-600">查看 →</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {showReportModal && reportPatient && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <div className="relative max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl bg-white p-8 shadow-xl">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900">历史报告文件</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {reportPatient.name || reportPatient.patient_id}
                  </p>
                </div>
                <button
                  className="rounded-full bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                  onClick={() => {
                    setShowReportModal(false);
                    flashSuccessButton();
                  }}
                >
                  关闭
                </button>
              </div>

              {/* 日期范围过滤器 */}
              <div className="mb-6 rounded-xl border border-slate-200 bg-slate-50 p-4">
                <h3 className="mb-3 text-sm font-semibold text-slate-900">按日期搜索</h3>
                <div className="flex flex-wrap gap-3">
                  <div className="flex-1 min-w-[150px]">
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      起始日期
                    </label>
                    <input
                      type="date"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      value={reportDateFrom}
                      onChange={(e) => {
                        setReportDateFrom(e.target.value);
                        handleReportDateFilterChange();
                      }}
                    />
                  </div>
                  <div className="flex-1 min-w-[150px]">
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      结束日期
                    </label>
                    <input
                      type="date"
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
                      value={reportDateTo}
                      onChange={(e) => {
                        setReportDateTo(e.target.value);
                        handleReportDateFilterChange();
                      }}
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      className="rounded-lg bg-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-300"
                      onClick={() => {
                        setReportDateFrom("");
                        setReportDateTo("");
                        if (reportPatient) {
                          setReportFiles(filterReportsForPatient(reportFiles, reportPatient));
                        }
                        flashSuccessButton();
                      }}
                    >
                      重置过滤
                    </button>
                  </div>
                </div>
              </div>

              {reportLoading && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  正在加载报告文件...
                </div>
              )}

              {!reportLoading && reportError && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {reportError}
                </div>
              )}

              {!reportLoading && !reportError && reportFiles.length === 0 && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  暂无匹配的历史报告文件
                </div>
              )}

              {!reportLoading && !reportError && reportFiles.length > 0 && (
                <div className="mb-3 text-xs text-slate-500">
                  共找到 {reportFiles.length} 个匹配的报告文件
                </div>
              )}

              {!reportLoading && !reportError && reportFiles.length > 0 && (
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
                      {reportFiles.map((file) => (
                        <tr key={`${file.date}-${file.name}`} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-medium text-slate-900">{file.name}</td>
                          <td className="px-4 py-3 text-slate-700">{file.date}</td>
                          <td className="px-4 py-3 text-slate-700">{formatFileSize(file.size_bytes)}</td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap gap-2">
                              <button
                                className="rounded-full border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50"
                                onClick={() => handlePreviewReport(file)}
                              >
                                查看
                              </button>
                              <button
                                className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                                onClick={() => handlePrintReport(file)}
                              >
                                打印
                              </button>
                              <a
                                className="rounded-full border border-emerald-200 px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
                                href={buildReportDownloadUrl(file)}
                                download
                              >
                                下载
                              </a>
                              <button
                                className="rounded-full border border-rose-200 px-3 py-1 text-xs font-semibold text-rose-600 hover:bg-rose-50"
                                onClick={() => handleArchiveReport(file)}
                              >
                                归档
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}

        {showReportPreview && (
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4">
            <div className="relative max-h-[90vh] w-full max-w-4xl overflow-auto rounded-2xl bg-white p-8 shadow-xl">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-semibold text-slate-900">报告预览</h2>
                  {reportPreviewTitle && (
                    <p className="mt-1 text-sm text-slate-500">{reportPreviewTitle}</p>
                  )}
                </div>
                <button
                  className="rounded-full bg-slate-100 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-200"
                  onClick={() => {
                    setShowReportPreview(false);
                    flashSuccessButton();
                  }}
                >
                  关闭
                </button>
              </div>
              <div className="prose max-w-none" dangerouslySetInnerHTML={{ __html: reportPreviewHtml }} />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
