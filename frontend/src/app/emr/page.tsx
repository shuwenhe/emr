"use client";

import { useMemo, useState } from "react";

type EmrResponse = Record<string, unknown> | Array<Record<string, unknown>>;

const API_BASE = "http://localhost:8000";

export default function EmrPage() {
  const [recordId, setRecordId] = useState("");
  const [emrId, setEmrId] = useState("");
  const [patientId, setPatientId] = useState("");
  const [output, setOutput] = useState<EmrResponse | { error: string }>({
    error: "请先执行操作",
  });

  const outputText = useMemo(() => JSON.stringify(output, null, 2), [output]);

  async function postJson<T>(url: string, payload: Record<string, unknown>): Promise<T> {
    const response = await fetch(url, {
      method: "POST",
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
  }

  async function handleFetch() {
    if (!emrId.trim()) {
      setOutput({ error: "emr_id 不能为空" });
      return;
    }
    const response = await fetch(`${API_BASE}/emr/${emrId.trim()}`);
    setOutput((await response.json()) as EmrResponse);
  }

  async function handleList() {
    const query = patientId.trim()
      ? `?patient_id=${encodeURIComponent(patientId.trim())}`
      : "";
    const response = await fetch(`${API_BASE}/emr${query}`);
    setOutput((await response.json()) as EmrResponse);
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
            <h2 className="text-lg font-semibold text-slate-900">生成病历</h2>
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
              生成电子病历
            </button>
            <p className="mt-3 text-xs text-slate-500">
              将基于报告与方案自动生成 EMR
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
          <pre className="mt-4 min-h-[240px] whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-xs text-slate-100">
            {outputText}
          </pre>
        </section>
      </main>
    </div>
  );
}
