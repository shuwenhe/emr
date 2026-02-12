"use client";

import { useEffect, useRef, useState } from "react";

type Patient = {
  patient_id: string;
  name: string;
  gender: string;
  age: number;
};

type EmrRecord = {
  emr_id: string;
  patient_id: string;
  patient_name: string;
  diagnosis: string;
  risk_level: string;
  abnormal_regions: Array<{ region: string; avg_c: number; status: string }>;
  created_at: string;
};

type TreatmentPlan = {
  plan_id: string;
  emr_id: string;
  acupoints: Array<{ name: string; location: string; reason: string }>;
  temperature: number;
  duration: number;
  frequency: string;
  course: number;
  notes: string;
};

type LastEmrContext = {
  emr_id?: string;
  patient_id?: string;
  name?: string;
  gender?: string;
  age?: number;
};

type PatientFlowState = {
  currentPatientId?: string;
  currentPatient?: {
    patient_id?: string;
    name?: string;
    gender?: string;
    age?: number | null;
  };
};

const API_BASE = "http://localhost:8000";
const TREATMENT_STATE_KEY = "patient_flow_state_treatment";

export default function TreatmentPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [emrRecords, setEmrRecords] = useState<EmrRecord[]>([]);
  const [selectedEmrId, setSelectedEmrId] = useState("");
  const [treatmentPlan, setTreatmentPlan] = useState<TreatmentPlan | null>(null);
  const [generating, setGenerating] = useState(false);
  const [lastContext, setLastContext] = useState<LastEmrContext | null>(null);
  const [patientFlowState, setPatientFlowState] = useState<PatientFlowState | null>(null);
  const prefilledRef = useRef(false);

  useEffect(() => {
    fetchPatients();
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(TREATMENT_STATE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as Record<string, string>;
      if (data.selectedPatientId) setSelectedPatientId(data.selectedPatientId);
      if (data.selectedEmrId) setSelectedEmrId(data.selectedEmrId);
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        TREATMENT_STATE_KEY,
        JSON.stringify({
          selectedPatientId,
          selectedEmrId,
        })
      );
    } catch {
      // ignore storage errors
    }
  }, [selectedPatientId, selectedEmrId]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("last_emr_context");
      if (raw) {
        setLastContext(JSON.parse(raw) as LastEmrContext);
      }
    } catch {
      setLastContext(null);
    }
  }, []);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("patient_flow_state_patients");
      if (raw) {
        setPatientFlowState(JSON.parse(raw) as PatientFlowState);
      }
    } catch {
      setPatientFlowState(null);
    }
  }, []);

  async function fetchPatients() {
    try {
      const response = await fetch(`${API_BASE}/platform/summary`);
      const data = await response.json();
      setPatients(Array.isArray(data) ? data : []);
    } catch {
      setPatients([]);
    }
  }

  async function fetchEmrRecords(patientId: string) {
    try {
      const response = await fetch(`${API_BASE}/emr?patient_id=${encodeURIComponent(patientId)}`);
      const data = await response.json();
      const records = Array.isArray(data) ? data : [];
      setEmrRecords(records);
      if (lastContext?.emr_id) {
        const found = records.find((item: EmrRecord) => item.emr_id === lastContext.emr_id);
        if (found) {
          setSelectedEmrId(lastContext.emr_id || "");
        }
      }
    } catch {
      setEmrRecords([]);
    }
  }

  async function generateTreatmentPlan(emrId: string) {
    setGenerating(true);
    try {
      // 模拟生成治疗方案（实际应调用后端API）
      const response = await fetch(`${API_BASE}/emr/${emrId}`);
      const emr = await response.json();
      
      // 基于诊断结果生成灸疗方案
      const plan: TreatmentPlan = {
        plan_id: `PLAN-${Date.now()}`,
        emr_id: emrId,
        acupoints: generateAcupoints(emr),
        temperature: 45,
        duration: 20,
        frequency: "每日1次",
        course: 10,
        notes: "建议配合中医调理，保持良好作息"
      };
      
      setTreatmentPlan(plan);
    } catch (error) {
      console.error("生成治疗方案失败:", error);
    } finally {
      setGenerating(false);
    }
  }

  function generateAcupoints(emr: any): Array<{ name: string; location: string; reason: string }> {
    const acupoints: Array<{ name: string; location: string; reason: string }> = [];
    
    if (emr.report?.analysis?.regional_comparison?.abnormal_regions) {
      const regions = emr.report.analysis.regional_comparison.abnormal_regions;
      
      regions.forEach((region: any) => {
        const regionName = String(region.region || "");
        
        if (regionName.includes("head") || regionName.includes("颈")) {
          acupoints.push({
            name: "百会",
            location: "头顶正中线与两耳尖连线的交点",
            reason: "调节头部气血，缓解颈部异常温度"
          });
          acupoints.push({
            name: "风池",
            location: "颈后两侧凹陷处",
            reason: "疏风散寒，改善颈部血液循环"
          });
        }
        
        if (regionName.includes("shoulder") || regionName.includes("肩")) {
          acupoints.push({
            name: "肩井",
            location: "肩部最高处，大椎与肩峰连线中点",
            reason: "舒筋活络，缓解肩部不适"
          });
        }
        
        if (regionName.includes("back") || regionName.includes("背")) {
          acupoints.push({
            name: "大椎",
            location: "第7颈椎棘突下凹陷中",
            reason: "调和阴阳，改善背部温度异常"
          });
        }
        
        if (regionName.includes("abdomen") || regionName.includes("腹")) {
          acupoints.push({
            name: "神阙",
            location: "肚脐中央",
            reason: "温阳散寒，调理脾胃"
          });
          acupoints.push({
            name: "关元",
            location: "肚脐下3寸",
            reason: "培补元气，温养下焦"
          });
        }
      });
    }
    
    // 去重
    const uniqueAcupoints = acupoints.filter((point, index, self) =>
      index === self.findIndex((p) => p.name === point.name)
    );
    
    return uniqueAcupoints.length > 0 ? uniqueAcupoints : [
      {
        name: "足三里",
        location: "膝盖外侧下方3寸",
        reason: "强身健体，调理脾胃"
      }
    ];
  }

  function handlePatientChange(patientId: string) {
    setSelectedPatientId(patientId);
    setSelectedEmrId("");
    setTreatmentPlan(null);
    if (patientId) {
      fetchEmrRecords(patientId);
    } else {
      setEmrRecords([]);
    }
  }

  function handleEmrChange(emrId: string) {
    setSelectedEmrId(emrId);
    setTreatmentPlan(null);
  }

  useEffect(() => {
    if (selectedPatientId && emrRecords.length === 0) {
      fetchEmrRecords(selectedPatientId);
    }
  }, [selectedPatientId, emrRecords.length]);

  useEffect(() => {
    if (prefilledRef.current) {
      return;
    }
    if (patients.length === 0) {
      return;
    }
    let patientId = lastContext?.patient_id || patientFlowState?.currentPatientId || "";
    if (!patientId) {
      const fallback = patientFlowState?.currentPatient;
      const match = patients.find((p) => {
        if (!fallback?.name) return false;
        const nameMatch = p.name === fallback.name;
        const genderMatch = fallback.gender ? p.gender === fallback.gender : true;
        const ageMatch = typeof fallback.age === "number" ? p.age === fallback.age : true;
        return nameMatch && genderMatch && ageMatch;
      });
      patientId = match?.patient_id || "";
    }
    if (patientId) {
      prefilledRef.current = true;
      setSelectedPatientId(patientId);
      fetchEmrRecords(patientId);
    }
  }, [lastContext, patientFlowState, patients]);

  function handleGenerate() {
    if (selectedEmrId) {
      generateTreatmentPlan(selectedEmrId);
    }
  }

  function handleExportPlan() {
    if (!treatmentPlan) return;
    
    const blob = new Blob([JSON.stringify(treatmentPlan, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `treatment-plan-${treatmentPlan.plan_id}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-12">
        <header className="mb-8 space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">治疗方案生成</h1>
          <p className="text-slate-600">
            根据诊断结果自动生成艾灸治疗方案，包括穴位选择、治疗参数和疗程建议
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-2">
          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">选择患者与病历</h2>
            
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700">患者</label>
                <select
                  className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  value={selectedPatientId}
                  onChange={(e) => handlePatientChange(e.target.value)}
                >
                  <option value="">请选择患者</option>
                  {patients.map((patient) => (
                    <option key={patient.patient_id} value={patient.patient_id}>
                      {patient.name} - {patient.gender} - {patient.age}岁
                    </option>
                  ))}
                </select>
              </div>

              {emrRecords.length > 0 && (
                <div>
                  <label className="block text-sm font-medium text-slate-700">病历记录</label>
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    value={selectedEmrId}
                    onChange={(e) => handleEmrChange(e.target.value)}
                  >
                    <option value="">请选择病历</option>
                    {emrRecords.map((record) => (
                      <option key={record.emr_id} value={record.emr_id}>
                        {record.created_at} - {record.risk_level?.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <button
                className="w-full rounded-full bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-slate-300"
                onClick={handleGenerate}
                disabled={!selectedEmrId || generating}
              >
                {generating ? "生成中..." : "生成治疗方案"}
              </button>
            </div>
          </section>

          {treatmentPlan && (
            <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold text-slate-900">治疗方案</h2>
                <button
                  className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  onClick={handleExportPlan}
                >
                  导出方案
                </button>
              </div>

              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">方案编号</p>
                  <p className="mt-1 font-mono text-sm text-slate-900">{treatmentPlan.plan_id}</p>
                </div>

                <div className="rounded-xl border border-slate-200 p-4">
                  <h3 className="text-sm font-semibold text-slate-900">治疗参数</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div>
                      <p className="text-xs text-slate-500">温度</p>
                      <p className="text-base font-semibold text-slate-900">{treatmentPlan.temperature}°C</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">单次时长</p>
                      <p className="text-base font-semibold text-slate-900">{treatmentPlan.duration}分钟</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">频率</p>
                      <p className="text-base font-semibold text-slate-900">{treatmentPlan.frequency}</p>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500">疗程</p>
                      <p className="text-base font-semibold text-slate-900">{treatmentPlan.course}次</p>
                    </div>
                  </div>
                </div>

                <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                  <h3 className="text-sm font-semibold text-blue-900">注意事项</h3>
                  <p className="mt-2 text-sm text-blue-800">{treatmentPlan.notes}</p>
                </div>
              </div>
            </section>
          )}
        </div>

        {treatmentPlan && treatmentPlan.acupoints.length > 0 && (
          <section className="mt-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">推荐穴位</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {treatmentPlan.acupoints.map((point, idx) => (
                <div key={idx} className="rounded-xl border border-slate-200 p-4">
                  <h3 className="text-base font-semibold text-slate-900">{point.name}</h3>
                  <p className="mt-2 text-sm text-slate-600">
                    <span className="font-medium">位置：</span>
                    {point.location}
                  </p>
                  <p className="mt-2 text-sm text-slate-600">
                    <span className="font-medium">功效：</span>
                    {point.reason}
                  </p>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
