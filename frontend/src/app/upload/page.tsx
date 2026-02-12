"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

const API_BASE = "http://localhost:8000";
const UPLOAD_STATE_KEY = "patient_flow_state_upload";

export default function UploadPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [file, setFile] = useState<File | null>(null);
  const [deviceId, setDeviceId] = useState("");
  const [deviceModel, setDeviceModel] = useState("IR-Thermal-320");
  const [captureTime, setCaptureTime] = useState("");
  const [patientName, setPatientName] = useState("");
  const [gender, setGender] = useState("");
  const [age, setAge] = useState("");
  const [bodyPart, setBodyPart] = useState("全身");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{ record_id?: string; error?: string } | null>(null);

  useEffect(() => {
    const name = searchParams.get("name") || "";
    const genderParam = searchParams.get("gender") || "";
    const ageParam = searchParams.get("age") || "";
    const bodyPartParam = searchParams.get("body_part") || "全身";

    if (name) setPatientName(name);
    if (genderParam) setGender(genderParam === "男" ? "male" : genderParam === "女" ? "female" : genderParam);
    if (ageParam) setAge(ageParam);
    if (bodyPartParam) setBodyPart(bodyPartParam);
  }, [searchParams]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(UPLOAD_STATE_KEY);
      if (!raw) return;
      const data = JSON.parse(raw) as Record<string, string>;
      if (data.deviceId) setDeviceId(data.deviceId);
      if (data.deviceModel) setDeviceModel(data.deviceModel);
      if (data.captureTime) setCaptureTime(data.captureTime);
      if (data.patientName) setPatientName(data.patientName);
      if (data.gender) setGender(data.gender);
      if (data.age) setAge(data.age);
      if (data.bodyPart) setBodyPart(data.bodyPart);
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        UPLOAD_STATE_KEY,
        JSON.stringify({
          deviceId,
          deviceModel,
          captureTime,
          patientName,
          gender,
          age,
          bodyPart,
        })
      );
    } catch {
      // ignore storage errors
    }
  }, [deviceId, deviceModel, captureTime, patientName, gender, age, bodyPart]);

  useEffect(() => {
    if (result?.record_id) {
      router.push(`/emr?record_id=${result.record_id}`);
    }
  }, [result, router]);

  async function handleUpload() {
    if (!file || !deviceId || !captureTime) {
      setResult({ error: "请填写必填字段并选择文件" });
      return;
    }

    setUploading(true);
    setResult(null);

    const metadata = {
      device: {
        device_id: deviceId,
        model: deviceModel || undefined,
      },
      capture: {
        capture_time: captureTime,
        frame_rate_hz: 9.0,
        resolution: "320x240",
        distance_m: 1.2,
        emissivity: 0.98,
      },
      patient: patientName || gender || age || bodyPart ? {
        name: patientName || undefined,
        gender: gender || undefined,
        age: age ? parseInt(age) : undefined,
        body_part: bodyPart || undefined,
      } : undefined,
    };

    const formData = new FormData();
    formData.append("file", file);
    formData.append("metadata", JSON.stringify(metadata));

    try {
      const response = await fetch(`${API_BASE}/ingest`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      
      if (response.ok) {
        setResult({ record_id: data.record_id });
      } else {
        setResult({ error: data.detail || "上传失败" });
      }
    } catch (error) {
      setResult({ error: `上传失败: ${String(error)}` });
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="flex min-h-screen w-full flex-col gap-8 px-10 py-12">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold text-slate-900">数据上传</h1>
          <p className="text-slate-600">上传红外热成像数据并生成诊断报告</p>
        </header>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">文件选择</h2>
          <div className="mt-4">
            <label className="block text-sm font-medium text-slate-700">
              数据文件 <span className="text-red-500">*</span>
            </label>
            <input
              type="file"
              accept=".csv,.bin,.dat,.npy,.zip"
              className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <p className="mt-1 text-xs text-slate-500">
              支持格式：.csv, .bin, .dat, .npy, .zip
            </p>
          </div>
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">设备信息</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700">
                设备ID <span className="text-red-500">*</span>
              </label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={deviceId}
                onChange={(e) => setDeviceId(e.target.value)}
                placeholder="device-001"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">设备型号</label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={deviceModel}
                onChange={(e) => setDeviceModel(e.target.value)}
              />
            </div>
            <div className="lg:col-span-2">
              <label className="block text-sm font-medium text-slate-700">
                采集时间 <span className="text-red-500">*</span>
              </label>
              <input
                type="datetime-local"
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={captureTime}
                onChange={(e) => setCaptureTime(e.target.value + ":00")}
              />
            </div>
          </div>
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">患者信息（可选）</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-slate-700">姓名</label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={patientName}
                onChange={(e) => setPatientName(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">性别</label>
              <select
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={gender}
                onChange={(e) => setGender(e.target.value)}
              >
                <option value="">请选择</option>
                <option value="male">男</option>
                <option value="female">女</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">年龄</label>
              <input
                type="number"
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={age}
                onChange={(e) => setAge(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">采集部位</label>
              <input
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                value={bodyPart}
                onChange={(e) => setBodyPart(e.target.value)}
                placeholder="face / hand / body"
              />
            </div>
          </div>
        </section>

        <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <button
            className="w-full rounded-full bg-blue-600 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:bg-slate-300"
            onClick={handleUpload}
            disabled={uploading}
          >
            {uploading ? "上传中..." : "上传数据"}
          </button>

          {result && (
            <div className="mt-4">
              {result.error ? (
                <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                  <p className="text-sm font-semibold text-red-900">上传失败</p>
                  <p className="mt-1 text-sm text-red-700">{result.error}</p>
                </div>
              ) : (
                <div className="rounded-xl border border-green-200 bg-green-50 p-4">
                  <p className="text-sm font-semibold text-green-900">上传成功</p>
                  <p className="mt-1 font-mono text-xs text-green-700">
                    Record ID: {result.record_id}
                  </p>
                  <p className="mt-2 text-xs text-green-700">正在跳转到诊断分析...</p>
                </div>
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
