"use client";

import { useEffect, useState } from "react";

type Patient = {
  patient_id: string;
  name: string;
  gender: string;
  age: number;
};

type EmrRecord = {
  emr_id: string;
  patient_id: string;
  created_at: string;
  risk_level: string;
  thermal_marked_image?: string;
  temperature_metrics?: {
    min_c: number;
    max_c: number;
    avg_c: number;
    body_avg_temp_c: number;
  };
};

const API_BASE = "http://localhost:8000";

export default function ComparisonPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [emrRecords, setEmrRecords] = useState<EmrRecord[]>([]);
  const [beforeEmr, setBeforeEmr] = useState<EmrRecord | null>(null);
  const [afterEmr, setAfterEmr] = useState<EmrRecord | null>(null);
  const [comparison, setComparison] = useState<any>(null);

  useEffect(() => {
    fetchPatients();
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
      setEmrRecords(records.sort((a, b) => 
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      ));
    } catch {
      setEmrRecords([]);
    }
  }

  async function fetchEmrDetail(emrId: string): Promise<EmrRecord | null> {
    try {
      const response = await fetch(`${API_BASE}/emr/${emrId}`);
      const data = await response.json();
      return {
        emr_id: data.emr_id,
        patient_id: data.patient_id,
        created_at: data.created_at,
        risk_level: data.report?.analysis?.risk_level || "unknown",
        thermal_marked_image: data.report?.thermal_marked_image,
        temperature_metrics: data.report?.analysis?.temperature_metrics
      };
    } catch {
      return null;
    }
  }

  function handlePatientChange(patientId: string) {
    setSelectedPatientId(patientId);
    setBeforeEmr(null);
    setAfterEmr(null);
    setComparison(null);
    if (patientId) {
      fetchEmrRecords(patientId);
    } else {
      setEmrRecords([]);
    }
  }

  async function handleBeforeChange(emrId: string) {
    if (emrId) {
      const emr = await fetchEmrDetail(emrId);
      setBeforeEmr(emr);
      calculateComparison(emr, afterEmr);
    } else {
      setBeforeEmr(null);
      setComparison(null);
    }
  }

  async function handleAfterChange(emrId: string) {
    if (emrId) {
      const emr = await fetchEmrDetail(emrId);
      setAfterEmr(emr);
      calculateComparison(beforeEmr, emr);
    } else {
      setAfterEmr(null);
      setComparison(null);
    }
  }

  function calculateComparison(before: EmrRecord | null, after: EmrRecord | null) {
    if (!before || !after || !before.temperature_metrics || !after.temperature_metrics) {
      setComparison(null);
      return;
    }

    const avgDelta = after.temperature_metrics.avg_c - before.temperature_metrics.avg_c;
    const maxDelta = after.temperature_metrics.max_c - before.temperature_metrics.max_c;
    const bodyAvgDelta = after.temperature_metrics.body_avg_temp_c - before.temperature_metrics.body_avg_temp_c;

    const riskImprovement = getRiskImprovement(before.risk_level, after.risk_level);

    setComparison({
      avgDelta,
      maxDelta,
      bodyAvgDelta,
      riskImprovement,
      effectiveness: getEffectivenessLevel(avgDelta, riskImprovement)
    });
  }

  function getRiskImprovement(beforeRisk: string, afterRisk: string): string {
    const riskLevels = { low: 1, medium: 2, high: 3, unknown: 0 };
    const beforeLevel = riskLevels[beforeRisk as keyof typeof riskLevels] || 0;
    const afterLevel = riskLevels[afterRisk as keyof typeof riskLevels] || 0;

    if (afterLevel < beforeLevel) return "改善";
    if (afterLevel > beforeLevel) return "加重";
    return "稳定";
  }

  function getEffectivenessLevel(avgDelta: number, riskImprovement: string): string {
    if (riskImprovement === "改善" && avgDelta < 0) return "显著";
    if (riskImprovement === "改善" || avgDelta < -0.5) return "有效";
    if (riskImprovement === "稳定" && Math.abs(avgDelta) < 0.3) return "维持";
    return "需观察";
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-12">
        <header className="mb-8 space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">疗效对比分析</h1>
          <p className="text-slate-600">
            对比治疗前后的热成像数据，评估治疗效果
          </p>
        </header>

        <section className="mb-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">选择对比记录</h2>
          
          <div className="mt-4 grid gap-4 lg:grid-cols-3">
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
              <>
                <div>
                  <label className="block text-sm font-medium text-slate-700">治疗前记录</label>
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    value={beforeEmr?.emr_id || ""}
                    onChange={(e) => handleBeforeChange(e.target.value)}
                  >
                    <option value="">请选择</option>
                    {emrRecords.map((record) => (
                      <option key={record.emr_id} value={record.emr_id}>
                        {record.created_at}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700">治疗后记录</label>
                  <select
                    className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                    value={afterEmr?.emr_id || ""}
                    onChange={(e) => handleAfterChange(e.target.value)}
                  >
                    <option value="">请选择</option>
                    {emrRecords.map((record) => (
                      <option key={record.emr_id} value={record.emr_id}>
                        {record.created_at}
                      </option>
                    ))}
                  </select>
                </div>
              </>
            )}
          </div>
        </section>

        {comparison && (
          <section className="mb-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">对比结果</h2>
            
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">平均温度变化</p>
                <p className={`mt-1 text-2xl font-bold ${comparison.avgDelta < 0 ? 'text-green-600' : comparison.avgDelta > 0 ? 'text-red-600' : 'text-slate-900'}`}>
                  {comparison.avgDelta > 0 ? '+' : ''}{comparison.avgDelta.toFixed(2)}°C
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">最高温度变化</p>
                <p className={`mt-1 text-2xl font-bold ${comparison.maxDelta < 0 ? 'text-green-600' : comparison.maxDelta > 0 ? 'text-red-600' : 'text-slate-900'}`}>
                  {comparison.maxDelta > 0 ? '+' : ''}{comparison.maxDelta.toFixed(2)}°C
                </p>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">风险等级</p>
                <p className={`mt-1 text-xl font-bold uppercase ${
                  comparison.riskImprovement === '改善' ? 'text-green-600' : 
                  comparison.riskImprovement === '加重' ? 'text-red-600' : 'text-slate-900'
                }`}>
                  {comparison.riskImprovement}
                </p>
              </div>

              <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <p className="text-xs font-medium uppercase tracking-wide text-blue-600">疗效评估</p>
                <p className="mt-1 text-xl font-bold text-blue-900">{comparison.effectiveness}</p>
              </div>
            </div>
          </section>
        )}

        {beforeEmr && afterEmr && (
          <section className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <h3 className="text-lg font-semibold text-slate-900">治疗前</h3>
              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">采集时间</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">{beforeEmr.created_at}</p>
                </div>
                {beforeEmr.temperature_metrics && (
                  <div className="rounded-xl border border-slate-200 p-4">
                    <h4 className="text-sm font-semibold text-slate-900">温度指标</h4>
                    <div className="mt-3 space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">平均温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {beforeEmr.temperature_metrics.avg_c.toFixed(2)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">最高温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {beforeEmr.temperature_metrics.max_c.toFixed(2)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">身体平均温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {beforeEmr.temperature_metrics.body_avg_temp_c.toFixed(2)}°C
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                {beforeEmr.thermal_marked_image && (
                  <img
                    src={`${API_BASE}/${beforeEmr.thermal_marked_image}`}
                    alt="治疗前热成像"
                    className="w-full rounded-xl border border-slate-200"
                  />
                )}
              </div>
            </div>

            <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
              <h3 className="text-lg font-semibold text-slate-900">治疗后</h3>
              <div className="mt-4 space-y-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-xs text-slate-500">采集时间</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">{afterEmr.created_at}</p>
                </div>
                {afterEmr.temperature_metrics && (
                  <div className="rounded-xl border border-slate-200 p-4">
                    <h4 className="text-sm font-semibold text-slate-900">温度指标</h4>
                    <div className="mt-3 space-y-2">
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">平均温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {afterEmr.temperature_metrics.avg_c.toFixed(2)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">最高温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {afterEmr.temperature_metrics.max_c.toFixed(2)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">身体平均温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {afterEmr.temperature_metrics.body_avg_temp_c.toFixed(2)}°C
                        </span>
                      </div>
                    </div>
                  </div>
                )}
                {afterEmr.thermal_marked_image && (
                  <img
                    src={`${API_BASE}/${afterEmr.thermal_marked_image}`}
                    alt="治疗后热成像"
                    className="w-full rounded-xl border border-slate-200"
                  />
                )}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
