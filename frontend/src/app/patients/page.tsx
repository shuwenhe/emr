"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

type Patient = {
  patient_id: string;
  name: string | null;
  gender: string | null;
  age: number | null;
  updated_at: string;
};

type EmrRecord = {
  emr_id: string;
  record_id: string;
  created_at: string;
  diagnosis: string | null;
  archived: boolean;
};

const API_BASE = "http://localhost:8000";

export default function PatientsPage() {
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<string | null>(null);
  const [emrs, setEmrs] = useState<EmrRecord[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    fetchPatients();
  }, []);

  async function fetchPatients() {
    try {
      const response = await fetch(`${API_BASE}/platform/summary`);
      const data = await response.json();
      if (data.patients && Array.isArray(data.patients)) {
        setPatients(data.patients);
      }
    } catch {
      setPatients([]);
    }
  }

  async function fetchPatientEmrs(patientId: string) {
    try {
      const response = await fetch(`${API_BASE}/emr?patient_id=${encodeURIComponent(patientId)}`);
      const data = await response.json();
      setEmrs(Array.isArray(data) ? data : []);
      setSelectedPatient(patientId);
    } catch {
      setEmrs([]);
    }
  }

  const filteredPatients = patients.filter((p) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      (p.patient_id && p.patient_id.toLowerCase().includes(query)) ||
      (p.name && p.name.toLowerCase().includes(query))
    );
  });

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="flex min-h-screen w-full flex-col gap-8 px-10 py-12">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">患者管理</h1>
          <p className="text-slate-600">查看患者列表与历史病历记录</p>
        </header>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <div className="mb-4">
            <input
              className="w-full max-w-md rounded-lg border border-slate-200 px-4 py-2 text-sm"
              placeholder="搜索患者ID或姓名..."
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
                    <th className="px-4 py-3 font-medium">更新时间</th>
                    <th className="px-4 py-3 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {filteredPatients.map((patient) => (
                    <tr key={patient.patient_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-mono text-xs text-slate-700">
                        {patient.patient_id}
                      </td>
                      <td className="px-4 py-3 text-slate-900">
                        {patient.name || "-"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {patient.gender || "-"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {patient.age || "-"}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {patient.updated_at || "-"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                          onClick={() => fetchPatientEmrs(patient.patient_id)}
                        >
                          查看病历
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500">暂无患者数据</p>
          )}
        </section>

        {selectedPatient && (
          <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-lg font-semibold text-slate-900">
              患者病历记录 ({selectedPatient})
            </h2>
            {emrs.length > 0 ? (
              <div className="mt-4 space-y-3">
                {emrs.map((emr) => (
                  <div
                    key={emr.emr_id}
                    className="flex items-center justify-between rounded-xl border border-slate-200 p-4"
                  >
                    <div className="flex-1">
                      <p className="font-mono text-xs text-slate-500">{emr.emr_id}</p>
                      <p className="mt-1 text-sm font-semibold text-slate-900">
                        {emr.diagnosis || "无诊断"}
                      </p>
                      <p className="mt-1 text-xs text-slate-600">{emr.created_at}</p>
                    </div>
                    <div className="flex gap-2">
                      {emr.archived && (
                        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                          已存档
                        </span>
                      )}
                      <Link
                        href={`/emr?emr_id=${emr.emr_id}`}
                        className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        查看详情
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-4 text-sm text-slate-500">该患者暂无病历记录</p>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
