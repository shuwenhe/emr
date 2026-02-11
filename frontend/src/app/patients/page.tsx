"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

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

export default function PatientsPage() {
  const router = useRouter();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);
  const [emrs, setEmrs] = useState<EmrRecord[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [showRegisterForm, setShowRegisterForm] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
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
    fetchPatients();
  }, []);

  async function fetchPatients() {
    try {
      // 首先获取已注册的患者
      const patientsResponse = await fetch(`${API_BASE}/patients`);
      const registeredPatients = await patientsResponse.json();
      
      // 然后从EMR记录中提取患者信息（用于补充未注册的患者）
      const emrResponse = await fetch(`${API_BASE}/emr`);
      const emrData = await emrResponse.json();
      
      const patientsMap = new Map<string, Patient>();
      
      // 先添加已注册的患者
      if (Array.isArray(registeredPatients)) {
        registeredPatients.forEach((patient: Patient) => {
          patientsMap.set(patient.patient_id, patient);
        });
      }
      
      // 再从EMR记录补充未注册的患者
      if (Array.isArray(emrData)) {
        emrData.forEach((emr: any) => {
          if (emr.patient) {
            const patientId = emr.patient.patient_id || emr.record_id;
            if (!patientsMap.has(patientId)) {
              patientsMap.set(patientId, {
                patient_id: patientId,
                name: emr.patient.name,
                gender: emr.patient.gender,
                age: emr.patient.age,
                updated_at: emr.created_at
              });
            }
          }
        });
      }
      
      setPatients(Array.from(patientsMap.values()));
    } catch (error) {
      console.error("获取患者列表失败:", error);
      setPatients([]);
    }
  }

  async function fetchPatientEmrs(patient: Patient) {
    try {
      const response = await fetch(`${API_BASE}/emr?patient_id=${encodeURIComponent(patient.patient_id)}`);
      const data = await response.json();
      setEmrs(Array.isArray(data) ? data : []);
      setSelectedPatient(patient);
      setShowDetailModal(true);
    } catch {
      setEmrs([]);
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
      await fetchPatients();
      
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
            onClick={() => setShowRegisterForm(true)}
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
                            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                            onClick={() => {
                              setSelectedPatient(patient);
                              setShowDetailModal(true);
                            }}
                          >
                            详情
                          </button>
                          <button
                            className="rounded-full border border-blue-200 px-3 py-1 text-xs font-semibold text-blue-600 hover:bg-blue-50"
                            onClick={() => fetchPatientEmrs(patient)}
                          >
                            病历
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
                onClick={() => setShowRegisterForm(true)}
              >
                立即登记患者
              </button>
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
                  onClick={() => setShowRegisterForm(false)}
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
                    onClick={() => setShowRegisterForm(false)}
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
                  onClick={() => setShowDetailModal(false)}
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
      </main>
    </div>
  );
}
