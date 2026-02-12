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

type LastEmrContext = {
  emr_id?: string;
  patient_id?: string;
  name?: string;
  gender?: string;
  age?: number;
};

const API_BASE = "http://localhost:8000";

export default function ComparisonPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState("");
  const [emrRecords, setEmrRecords] = useState<EmrRecord[]>([]);
  const [beforeEmr, setBeforeEmr] = useState<EmrRecord | null>(null);
  const [afterEmr, setAfterEmr] = useState<EmrRecord | null>(null);
  const [comparison, setComparison] = useState<any>(null);
  const [lastContext, setLastContext] = useState<LastEmrContext | null>(null);
  const [autoCompared, setAutoCompared] = useState(false);
  const [autoLoadComplete, setAutoLoadComplete] = useState(false);

  useEffect(() => {
    // 读取所有可能包含患者信息的 localStorage keys
    try {
      const uploadState = localStorage.getItem("patient_flow_state_upload");
      const lastEmrContext = localStorage.getItem("last_emr_context");
      const patientsState = localStorage.getItem("patient_flow_state_patients");
      const emrState = localStorage.getItem("patient_flow_state_emr");
      
      console.log("=== Checking all localStorage for patient info ===");
      console.log("Upload state:", uploadState);
      console.log("Last EMR context:", lastEmrContext);
      console.log("Patients state:", patientsState);
      console.log("EMR state:", emrState);
      
      let contextToUse: LastEmrContext | null = null;
      
      // 优先使用 last_emr_context（最新的诊断信息）
      if (lastEmrContext) {
        const context = JSON.parse(lastEmrContext) as LastEmrContext;
        console.log("Using last_emr_context:", context);
        contextToUse = context;
      }
      // 其次使用 patient_flow_state_patients（患者列表页）
      else if (patientsState) {
        const state = JSON.parse(patientsState);
        console.log("Using patients state:", state);
        if (state.currentPatientId || state.currentPatient) {
          contextToUse = {
            patient_id: state.currentPatientId || state.currentPatient?.patient_id,
            name: state.currentPatient?.name,
            gender: state.currentPatient?.gender,
            age: state.currentPatient?.age
          };
        }
      }
      // 再次使用 patient_flow_state_upload（上传页）
      else if (uploadState) {
        const state = JSON.parse(uploadState);
        console.log("Using upload state:", state);
        contextToUse = {
          patient_id: state.selectedPatientId,
          name: state.patientName,
          gender: state.gender,
          age: state.age ? parseInt(state.age) : undefined
        };
      }
      // 最后尝试 emr state
      else if (emrState) {
        const state = JSON.parse(emrState);
        console.log("Using EMR state:", state);
        if (state.currentPatientId || state.currentPatient) {
          contextToUse = {
            patient_id: state.currentPatientId || state.currentPatient?.patient_id,
            name: state.currentPatient?.name,
            gender: state.currentPatient?.gender,
            age: state.currentPatient?.age
          };
        }
      }
      
      console.log("Final context to use:", contextToUse);
      setLastContext(contextToUse);
    } catch (error) {
      console.error("Failed to load patient context:", error);
      setLastContext(null);
    }
    
    fetchPatients();
  }, []);

  async function fetchPatients() {
    try {
      const response = await fetch(`${API_BASE}/patients`);
      const data = await response.json();
      console.log("Fetched patients from API:", data);
      setPatients(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error("Failed to fetch patients:", error);
      setPatients([]);
    }
  }

  async function fetchEmrRecords(patientId: string) {
    console.log("=== Fetching EMR records ===");
    console.log("Patient ID:", patientId);
    
    try {
      const url = `${API_BASE}/emr?patient_id=${encodeURIComponent(patientId)}`;
      console.log("Fetching from URL:", url);
      
      const response = await fetch(url);
      console.log("Response status:", response.status, response.statusText);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      const data = await response.json();
      console.log("Raw EMR data received:", data);
      console.log("Is array:", Array.isArray(data));
      console.log("Data length:", Array.isArray(data) ? data.length : 'N/A');
      
      const records = Array.isArray(data) ? data : [];
      
      if (records.length > 0) {
        console.log("Sample EMR record:", records[0]);
        console.log("All EMR IDs:", records.map((r: any) => r.emr_id));
        console.log("All creation dates:", records.map((r: any) => r.created_at));
      }
      
      const sortedRecords = records.sort((a, b) => 
        new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
      
      console.log("Sorted records count:", sortedRecords.length);
      setEmrRecords(sortedRecords);
      
      // 自动对比：如果有至少2条记录，自动选择倒数第二条和最后一条
      if (sortedRecords.length >= 2) {
        const secondLast = sortedRecords[sortedRecords.length - 2];
        const last = sortedRecords[sortedRecords.length - 1];
        
        console.log("Auto-comparing EMRs:", secondLast.emr_id, "vs", last.emr_id);
        
        const beforeEmrData = await fetchEmrDetail(secondLast.emr_id);
        const afterEmrData = await fetchEmrDetail(last.emr_id);
        
        console.log("Before EMR data:", beforeEmrData);
        console.log("After EMR data:", afterEmrData);
        
        if (beforeEmrData && afterEmrData) {
          setBeforeEmr(beforeEmrData);
          setAfterEmr(afterEmrData);
          calculateComparison(beforeEmrData, afterEmrData);
          setAutoCompared(true);
        } else {
          console.warn("Failed to fetch EMR details for comparison");
        }
      } else {
        console.log("Not enough EMR records for auto-comparison (need at least 2)");
      }
    } catch (error) {
      console.error("Failed to fetch EMR records:", error);
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
    console.log("Patient changed to:", patientId);
    setSelectedPatientId(patientId);
    setBeforeEmr(null);
    setAfterEmr(null);
    setComparison(null);
    setAutoCompared(false);
    if (patientId) {
      fetchEmrRecords(patientId);
    } else {
      setEmrRecords([]);
    }
  }

  // 自动加载患者和对比数据
  useEffect(() => {
    console.log("=== Auto-load effect triggered ===");
    console.log("Patients count:", patients.length);
    console.log("Last context:", lastContext);
    console.log("Selected patient ID:", selectedPatientId);
    console.log("Auto load complete:", autoLoadComplete);
    
    if (autoLoadComplete) {
      console.log("Auto-load already completed, skipping");
      return;
    }
    if (patients.length === 0) {
      console.log("No patients loaded yet, waiting...");
      return;
    }
    if (!lastContext) {
      console.log("No context available");
      return;
    }
    
    let targetPatient: Patient | undefined;
    
    // 优先使用 patient_id 精确匹配
    if (lastContext.patient_id) {
      targetPatient = patients.find(p => p.patient_id === lastContext.patient_id);
      console.log("Match by patient_id:", targetPatient);
    }
    
    // 如果没匹配到，尝试用姓名匹配（宽松匹配）
    if (!targetPatient && lastContext.name) {
      // 先尝试精确匹配
      targetPatient = patients.find(p => p.name === lastContext.name);
      console.log("Match by exact name:", targetPatient);
      
      // 如果还没匹配到，尝试忽略空格和大小写
      if (!targetPatient) {
        const normalizedName = lastContext.name.trim().toLowerCase();
        targetPatient = patients.find(p => 
          p.name?.trim().toLowerCase() === normalizedName
        );
        console.log("Match by normalized name:", targetPatient);
      }
      
      // 如果找到多个同名患者，进一步用性别和年龄过滤
      if (targetPatient) {
        const sameNamePatients = patients.filter(p => 
          p.name?.trim().toLowerCase() === lastContext.name?.trim().toLowerCase()
        );
        
        if (sameNamePatients.length > 1) {
          console.log("Multiple patients with same name:", sameNamePatients);
          
          // 尝试用性别+年龄进一步过滤
          const filtered = sameNamePatients.find(p => {
            const genderMatch = !lastContext.gender || 
              p.gender === lastContext.gender || 
              (p.gender === "male" && lastContext.gender === "男") ||
              (p.gender === "female" && lastContext.gender === "女") ||
              (p.gender === "男" && lastContext.gender === "male") ||
              (p.gender === "女" && lastContext.gender === "female");
            const ageMatch = !lastContext.age || p.age === lastContext.age;
            return genderMatch && ageMatch;
          });
          
          if (filtered) {
            targetPatient = filtered;
            console.log("Filtered by gender/age:", targetPatient);
          }
        }
      }
    }
    
    if (targetPatient) {
      console.log("✓ Auto-selecting patient:", targetPatient);
      setSelectedPatientId(targetPatient.patient_id);
      setAutoLoadComplete(true);
      fetchEmrRecords(targetPatient.patient_id);
    } else {
      console.warn("✗ No matching patient found");
      console.log("Available patients:", patients.map(p => ({
        id: p.patient_id,
        name: p.name,
        gender: p.gender,
        age: p.age
      })));
    }
  }, [patients, lastContext, autoLoadComplete]);

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
    console.log("Calculating comparison...");
    console.log("Before metrics:", before?.temperature_metrics);
    console.log("After metrics:", after?.temperature_metrics);
    
    if (!before || !after || !before.temperature_metrics || !after.temperature_metrics) {
      console.warn("Cannot calculate comparison: missing data or temperature metrics");
      setComparison(null);
      return;
    }

    const avgDelta = after.temperature_metrics.avg_c - before.temperature_metrics.avg_c;
    const maxDelta = after.temperature_metrics.max_c - before.temperature_metrics.max_c;
    const bodyAvgDelta = after.temperature_metrics.body_avg_temp_c - before.temperature_metrics.body_avg_temp_c;

    const riskImprovement = getRiskImprovement(before.risk_level, after.risk_level);

    const comparisonResult = {
      avgDelta,
      maxDelta,
      bodyAvgDelta,
      riskImprovement,
      effectiveness: getEffectivenessLevel(avgDelta, riskImprovement)
    };
    
    console.log("Comparison result:", comparisonResult);
    setComparison(comparisonResult);
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

  function formatTemp(value?: number) {
    return typeof value === "number" ? value.toFixed(2) : "-";
  }

  function formatGender(value?: string) {
    if (!value) return "-";
    const normalized = String(value).toLowerCase();
    if (normalized === "male" || normalized === "m" || value === "男") return "男";
    if (normalized === "female" || normalized === "f" || value === "女") return "女";
    return String(value);
  }

  function buildComparisonPayload() {
    const patient = patients.find((item) => item.patient_id === selectedPatientId);
    return {
      patient: patient
        ? {
            patient_id: patient.patient_id,
            name: patient.name,
            gender: patient.gender,
            age: patient.age,
          }
        : null,
      before: beforeEmr,
      after: afterEmr,
      comparison,
      generated_at: new Date().toISOString(),
    };
  }

  async function handleExportComparison() {
    if (!comparison || !beforeEmr || !afterEmr) return;
    const patient = patients.find((item) => item.patient_id === selectedPatientId);
    const docx = await import("docx");
    const {
      Document,
      Packer,
      Paragraph,
      TextRun,
      HeadingLevel,
      Table,
      TableRow,
      TableCell,
      WidthType,
    } = docx;

    const rows = (title: string, data: Array<[string, string]>) =>
      new Table({
        width: { size: 100, type: WidthType.PERCENTAGE },
        rows: [
          new TableRow({
            children: [
              new TableCell({
                width: { size: 30, type: WidthType.PERCENTAGE },
                children: [new Paragraph({ text: title })],
              }),
              new TableCell({
                width: { size: 70, type: WidthType.PERCENTAGE },
                children: [new Paragraph({ text: "" })],
              }),
            ],
          }),
          ...data.map(
            ([label, value]) =>
              new TableRow({
                children: [
                  new TableCell({
                    width: { size: 30, type: WidthType.PERCENTAGE },
                    children: [new Paragraph({ text: label })],
                  }),
                  new TableCell({
                    width: { size: 70, type: WidthType.PERCENTAGE },
                    children: [new Paragraph({ text: value })],
                  }),
                ],
              })
          ),
        ],
      });

    const comparisonRows: Array<[string, string]> = [
      ["平均温度变化", `${comparison.avgDelta > 0 ? "+" : ""}${comparison.avgDelta.toFixed(2)}°C`],
      ["最高温度变化", `${comparison.maxDelta > 0 ? "+" : ""}${comparison.maxDelta.toFixed(2)}°C`],
      ["风险等级", comparison.riskImprovement],
      ["疗效评估", comparison.effectiveness],
    ];

    const beforeRows: Array<[string, string]> = [
      ["采集时间", beforeEmr.created_at],
      ["平均温度", `${formatTemp(beforeEmr.temperature_metrics?.avg_c)}°C`],
      ["最高温度", `${formatTemp(beforeEmr.temperature_metrics?.max_c)}°C`],
      ["身体平均温度", `${formatTemp(beforeEmr.temperature_metrics?.body_avg_temp_c)}°C`],
    ];

    const afterRows: Array<[string, string]> = [
      ["采集时间", afterEmr.created_at],
      ["平均温度", `${formatTemp(afterEmr.temperature_metrics?.avg_c)}°C`],
      ["最高温度", `${formatTemp(afterEmr.temperature_metrics?.max_c)}°C`],
      ["身体平均温度", `${formatTemp(afterEmr.temperature_metrics?.body_avg_temp_c)}°C`],
    ];

    const header = new Paragraph({
      text: "疗效对比分析",
      heading: HeadingLevel.HEADING_1,
    });

    const metaText = patient
      ? `患者：${patient.name} · ${formatGender(patient.gender)} · ${patient.age}岁 · ID: ${patient.patient_id}`
      : "患者：-";

    const doc = new Document({
      sections: [
        {
          children: [
            header,
            new Paragraph({ text: `生成时间：${new Date().toLocaleString()}` }),
            new Paragraph({ text: metaText }),
            new Paragraph({ text: "" }),
            new Paragraph({ text: "对比结果", heading: HeadingLevel.HEADING_2 }),
            rows("", comparisonRows),
            new Paragraph({ text: "" }),
            new Paragraph({ text: "治疗前", heading: HeadingLevel.HEADING_2 }),
            rows("", beforeRows),
            new Paragraph({ text: "" }),
            new Paragraph({ text: "治疗后", heading: HeadingLevel.HEADING_2 }),
            rows("", afterRows),
          ],
        },
      ],
    });

    const blob = await Packer.toBlob(doc);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `comparison-${beforeEmr.emr_id}-${afterEmr.emr_id}.docx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
  }

  function handlePrintComparison() {
    if (!comparison || !beforeEmr || !afterEmr) return;
    const patient = patients.find((item) => item.patient_id === selectedPatientId);
    const printWindow = window.open("", "_blank", "width=900,height=700");
    if (!printWindow) return;
    const html = `
      <!doctype html>
      <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <title>疗效对比分析</title>
          <style>
            @page { margin: 0; }
            @media print { body { margin: 1.6cm; } }
            body { font-family: "PingFang SC", "Helvetica Neue", Arial, sans-serif; color: #0f172a; }
            h1 { font-size: 20px; margin-bottom: 8px; }
            h2 { font-size: 16px; margin: 16px 0 8px; }
            .meta { color: #475569; font-size: 12px; margin-bottom: 12px; }
            .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
            .card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 12px; }
          </style>
        </head>
        <body>
          <h1>疗效对比分析</h1>
          <div class="meta">生成时间：${new Date().toLocaleString()}</div>
          ${patient ? `<div class="meta">患者：${patient.name} · ${formatGender(patient.gender)} · ${patient.age}岁 · ID: ${patient.patient_id}</div>` : ""}
          <h2>对比结果</h2>
          <div class="grid">
            <div class="card">平均温度变化：${comparison.avgDelta > 0 ? "+" : ""}${comparison.avgDelta.toFixed(2)}°C</div>
            <div class="card">最高温度变化：${comparison.maxDelta > 0 ? "+" : ""}${comparison.maxDelta.toFixed(2)}°C</div>
            <div class="card">风险等级：${comparison.riskImprovement}</div>
            <div class="card">疗效评估：${comparison.effectiveness}</div>
          </div>
          <h2>治疗前</h2>
          <div class="grid">
            <div class="card">采集时间：${beforeEmr.created_at}</div>
            <div class="card">平均温度：${formatTemp(beforeEmr.temperature_metrics?.avg_c)}°C</div>
            <div class="card">最高温度：${formatTemp(beforeEmr.temperature_metrics?.max_c)}°C</div>
            <div class="card">身体平均温度：${formatTemp(beforeEmr.temperature_metrics?.body_avg_temp_c)}°C</div>
          </div>
          <h2>治疗后</h2>
          <div class="grid">
            <div class="card">采集时间：${afterEmr.created_at}</div>
            <div class="card">平均温度：${formatTemp(afterEmr.temperature_metrics?.avg_c)}°C</div>
            <div class="card">最高温度：${formatTemp(afterEmr.temperature_metrics?.max_c)}°C</div>
            <div class="card">身体平均温度：${formatTemp(afterEmr.temperature_metrics?.body_avg_temp_c)}°C</div>
          </div>
        </body>
      </html>
    `;
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-12">
        <header className="mb-8 space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">疗效对比分析</h1>
          <p className="text-slate-600">
            对比治疗前后的热成像数据，评估治疗效果
          </p>
          {process.env.NODE_ENV === 'development' && (
            <div className="mt-2 rounded border border-gray-300 bg-gray-50 p-2 text-xs text-gray-600">
              <div className="font-semibold mb-1">调试信息:</div>
              <div>• 患者总数: {patients.length}</div>
              <div>• 选中患者ID: {selectedPatientId || '无'}</div>
              <div>• EMR记录数: {emrRecords.length}</div>
              <div>• 自动加载完成: {autoLoadComplete ? '是' : '否'}</div>
              {lastContext && (
                <div className="mt-1 border-t border-gray-300 pt-1">
                  <div className="font-semibold">上下文信息:</div>
                  <div>• Patient ID: {lastContext.patient_id || '无'}</div>
                  <div>• 姓名: {lastContext.name || '无'}</div>
                  <div>• 性别: {lastContext.gender || '无'}</div>
                  <div>• 年龄: {lastContext.age || '无'}</div>
                </div>
              )}
              {!lastContext && (
                <div className="mt-1 text-yellow-600">• 未检测到上下文信息</div>
              )}
            </div>
          )}
        </header>

        <section className="mb-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">对比患者信息</h2>
          
          {selectedPatientId && patients.length > 0 && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
              <div className="flex items-center justify-between">
                <div className="flex-1">
                  <p className="text-sm font-medium text-blue-900">
                    {patients.find(p => p.patient_id === selectedPatientId)?.name || '未知患者'}
                  </p>
                  <p className="mt-1 text-xs text-blue-700">
                    {(() => {
                      const patient = patients.find(p => p.patient_id === selectedPatientId);
                      if (!patient) return '';
                      const genderText = patient.gender === 'male' || patient.gender === '男' ? '男' : 
                                        patient.gender === 'female' || patient.gender === '女' ? '女' : patient.gender;
                      return `${genderText} · ${patient.age}岁 · 患者ID: ${patient.patient_id}`;
                    })()}
                  </p>
                  {emrRecords.length > 0 && (
                    <p className="mt-1 text-xs text-blue-600">
                      ✓ 已找到 {emrRecords.length} 条诊断报告
                    </p>
                  )}
                  {emrRecords.length === 0 && selectedPatientId && (
                    <p className="mt-1 text-xs text-red-600">
                      ⚠ 未找到诊断报告（正在查询中...）
                    </p>
                  )}
                </div>
                <button
                  className="text-xs text-blue-600 hover:text-blue-800 underline"
                  onClick={() => {
                    setSelectedPatientId("");
                    setEmrRecords([]);
                    setBeforeEmr(null);
                    setAfterEmr(null);
                    setComparison(null);
                    setAutoCompared(false);
                    setAutoLoadComplete(false);
                  }}
                >
                  切换患者
                </button>
              </div>
            </div>
          )}
          
          {!selectedPatientId && patients.length > 0 && (
            <div className="mt-4 space-y-3">
              <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-3 text-sm text-yellow-700">
                未检测到最近使用的患者信息。请从下方列表选择一个患者进行疗效对比。
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  选择患者进行对比 ({patients.length} 名)
                </label>
                <select
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                  value=""
                  onChange={(e) => {
                    if (e.target.value) {
                      handlePatientChange(e.target.value);
                      setAutoLoadComplete(true);
                    }
                  }}
                >
                  <option value="">请选择患者</option>
                  {patients.map((patient) => (
                    <option key={patient.patient_id} value={patient.patient_id}>
                      {patient.name} - {formatGender(patient.gender)} - {patient.age}岁
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
          
          {!selectedPatientId && patients.length === 0 && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-sm text-red-700">
              系统中暂无患者数据，请先在"患者登记"或"数据上传"页面添加患者。
            </div>
          )}
          
          {autoCompared && comparison && (
            <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-3 py-3 text-sm text-green-700">
              ✓ 系统已自动对比该患者最近两次诊断报告，展示治疗效果。
            </div>
          )}
          
          {selectedPatientId && emrRecords.length > 0 && emrRecords.length < 2 && (
            <div className="mt-4 rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-3 text-sm text-yellow-700">
              当前患者仅有 {emrRecords.length} 条诊断报告，需要至少2条报告才能进行疗效对比。
              请为该患者进行第二次数据采集后再查看疗效对比。
            </div>
          )}
          
          {selectedPatientId && emrRecords.length === 0 && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-3">
              <p className="text-sm font-semibold text-red-900">该患者暂无诊断报告记录</p>
              <p className="mt-1 text-xs text-red-700">
                可能原因：
              </p>
              <ul className="mt-1 text-xs text-red-700 list-disc list-inside space-y-1">
                <li>该患者还未进行数据采集和诊断分析</li>
                <li>诊断报告关联的患者ID与当前患者ID不匹配</li>
                <li>数据库查询失败（请查看浏览器控制台）</li>
              </ul>
              <p className="mt-2 text-xs text-red-700">
                请查看浏览器控制台（F12）的详细日志进行排查。
              </p>
            </div>
          )}
        </section>

        {selectedPatientId && emrRecords.length >= 2 && (
          <section className="mb-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">选择对比记录（可选）</h2>
            <p className="mt-1 text-sm text-slate-600">默认对比最近两次记录，也可手动选择其他记录进行对比</p>
            
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
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
            </div>
          </section>
        )}

        {comparison && (
          <section className="mb-6 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-900">对比结果</h2>
              <div className="flex items-center gap-3">
                <button
                  className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  onClick={handleExportComparison}
                >
                  导出
                </button>
                <button
                  className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  onClick={handlePrintComparison}
                >
                  打印
                </button>
              </div>
            </div>
            
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
                          {formatTemp(beforeEmr.temperature_metrics.avg_c)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">最高温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {formatTemp(beforeEmr.temperature_metrics.max_c)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">身体平均温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {formatTemp(beforeEmr.temperature_metrics.body_avg_temp_c)}°C
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
                          {formatTemp(afterEmr.temperature_metrics.avg_c)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">最高温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {formatTemp(afterEmr.temperature_metrics.max_c)}°C
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-sm text-slate-600">身体平均温度</span>
                        <span className="text-sm font-semibold text-slate-900">
                          {formatTemp(afterEmr.temperature_metrics.body_avg_temp_c)}°C
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
