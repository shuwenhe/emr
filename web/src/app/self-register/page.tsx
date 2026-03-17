"use client";

import { FormEvent, useMemo, useState } from "react";

type RegisterForm = {
  name: string;
  phone: string;
  gender: string;
  age: string;
};

const API_BASE = "";

export default function SelfRegisterPage() {
  const [form, setForm] = useState<RegisterForm>({
    name: "",
    phone: "",
    gender: "男",
    age: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [successPatientId, setSuccessPatientId] = useState("");
  const [error, setError] = useState("");

  const canSubmit = useMemo(() => {
    return form.name.trim().length > 0 && form.phone.trim().length > 0;
  }, [form.name, form.phone]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError("");
    setSuccessPatientId("");

    try {
      const response = await fetch(`${API_BASE}/api/patients`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name.trim(),
          phone: form.phone.trim(),
          gender: form.gender,
          age: form.age ? Number(form.age) : undefined,
          department: "自助登记",
        }),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || "登记失败，请稍后重试");
      }

      setSuccessPatientId(String(data.patient_id || ""));
      setForm({ name: "", phone: "", gender: "男", age: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "登记失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-emerald-50 to-white px-4 py-8">
      <main className="mx-auto w-full max-w-md">
        <div className="rounded-2xl border border-emerald-100 bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-semibold text-slate-900">患者自助登记</h1>
          <p className="mt-2 text-sm text-slate-600">
            请填写姓名和电话，提交后前台可立即看到您的登记信息。
          </p>

          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-sm font-medium text-slate-700">姓名</label>
              <input
                type="text"
                required
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                placeholder="请输入姓名"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">手机号</label>
              <input
                type="tel"
                required
                value={form.phone}
                onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                placeholder="请输入手机号"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">性别</label>
              <select
                value={form.gender}
                onChange={(e) => setForm((prev) => ({ ...prev, gender: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 focus:border-emerald-500 focus:outline-none"
              >
                <option value="男">男</option>
                <option value="女">女</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">年龄</label>
              <input
                type="number"
                min={0}
                max={130}
                value={form.age}
                onChange={(e) => setForm((prev) => ({ ...prev, age: e.target.value }))}
                className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                placeholder="请输入年龄"
              />
            </div>

            <button
              type="submit"
              disabled={!canSubmit || submitting}
              className="w-full rounded-full bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-300"
            >
              {submitting ? "提交中..." : "提交登记"}
            </button>
          </form>

          {successPatientId && (
            <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
              登记成功，您的患者编号：{successPatientId}
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              {error}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
