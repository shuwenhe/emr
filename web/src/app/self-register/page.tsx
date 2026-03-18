"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type RegisterForm = {
  name: string;
  phone: string;
  gender: string;
  age: string;
};

const API_BASE = "";
const PHONE_DIGITS_REGEX = /^1\d{10}$/;
const REGISTER_TIMEOUT_MS = 25000;
const REGISTER_RETRY_COUNT = 1;

function isAbortError(err: unknown): boolean {
  if (!err) return false;
  if (err instanceof DOMException && err.name === "AbortError") return true;
  if (err instanceof Error && err.name === "AbortError") return true;
  const message = err instanceof Error ? err.message : String(err);
  return /abort/i.test(message);
}

export default function SelfRegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState<RegisterForm>({
    name: "",
    phone: "",
    gender: "男",
    age: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [successPatientId, setSuccessPatientId] = useState("");
  const [error, setError] = useState("");

  const nameValid = useMemo(() => form.name.trim().length >= 2, [form.name]);
  const phoneDigits = useMemo(() => form.phone.replace(/\D/g, ""), [form.phone]);
  const phoneValid = useMemo(() => PHONE_DIGITS_REGEX.test(phoneDigits), [phoneDigits]);
  const canSubmit = useMemo(() => nameValid && phoneValid, [nameValid, phoneValid]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    if (!nameValid) {
      setError("请填写至少 2 个字的姓名");
      return;
    }
    if (!phoneValid) {
      setError("请填写正确的 11 位手机号");
      return;
    }

    setSubmitting(true);
    setError("");
    setSuccessPatientId("");

    try {
      let response: Response | null = null;
      let lastError: unknown;
      for (let attempt = 0; attempt <= REGISTER_RETRY_COUNT; attempt += 1) {
        const controller = new AbortController();
        const timer = window.setTimeout(() => controller.abort(), REGISTER_TIMEOUT_MS);
        try {
          response = await fetch(`${API_BASE}/api/patients`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            signal: controller.signal,
            body: JSON.stringify({
              name: form.name.trim(),
              phone: phoneDigits,
              gender: form.gender,
              age: form.age ? Number(form.age) : undefined,
              department: "自助登记",
            }),
          });
          break;
        } catch (err) {
          lastError = err;
          if (attempt >= REGISTER_RETRY_COUNT) {
            throw err;
          }
        } finally {
          window.clearTimeout(timer);
        }
      }

      if (!response) {
        throw new Error(lastError instanceof Error ? lastError.message : "登记请求失败");
      }

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data?.detail || `登记失败（HTTP ${response.status}）`);
      }

      setSuccessPatientId(String(data.patient_id || ""));
      setForm({ name: "", phone: "", gender: "男", age: "" });
      const nextPatientId = String(data.patient_id || "").trim();
      if (nextPatientId) {
        window.setTimeout(() => {
          router.push(`/emr?patient_id=${encodeURIComponent(nextPatientId)}`);
        }, 600);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "登记失败，请稍后重试";
      if (isAbortError(err)) {
        setError("请求超时，请检查网络后重试");
      } else {
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#f4f7fb] px-4 py-7">
      <div className="pointer-events-none absolute -top-24 left-0 h-60 w-60 rounded-full bg-emerald-200/60 blur-3xl" />
      <div className="pointer-events-none absolute right-0 top-1/3 h-48 w-48 rounded-full bg-sky-200/70 blur-3xl" />

      <main className="relative mx-auto w-full max-w-md">
        <section className="rounded-[28px] border border-white/80 bg-white/95 p-6 shadow-[0_12px_40px_rgba(15,23,42,0.08)] backdrop-blur">
          <div className="mb-5 flex items-center justify-between">
            <h1 className="text-[38px] font-black leading-none tracking-tight text-slate-900">患者自助登记</h1>
            <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
              约 15 秒
            </span>
          </div>

          <p className="text-[17px] leading-relaxed text-slate-700">
            请填写姓名和电话，提交后前台会实时收到登记信息。
          </p>

          <form className="mt-6 space-y-4" onSubmit={handleSubmit} noValidate>
            <div>
              <label className="mb-1.5 block text-[15px] font-semibold text-slate-800">姓名</label>
              <input
                type="text"
                required
                autoComplete="name"
                value={form.name}
                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-[20px] leading-none text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:bg-white focus:outline-none"
                placeholder="请输入姓名"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-[15px] font-semibold text-slate-800">手机号</label>
              <input
                type="tel"
                required
                inputMode="numeric"
                autoComplete="tel"
                value={form.phone}
                onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3.5 text-[20px] leading-none text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:bg-white focus:outline-none"
                placeholder="请输入 11 位手机号"
              />
              {!phoneValid && form.phone.trim().length > 0 && (
                <p className="mt-1 text-xs text-rose-600">手机号格式不正确</p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1.5 block text-[15px] font-semibold text-slate-800">性别</label>
                <select
                  value={form.gender}
                  onChange={(e) => setForm((prev) => ({ ...prev, gender: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-[20px] leading-none text-slate-900 focus:border-emerald-500 focus:bg-white focus:outline-none"
                >
                  <option value="男">男</option>
                  <option value="女">女</option>
                </select>
              </div>

              <div>
                <label className="mb-1.5 block text-[15px] font-semibold text-slate-800">年龄</label>
                <input
                  type="number"
                  min={0}
                  max={130}
                  inputMode="numeric"
                  value={form.age}
                  onChange={(e) => setForm((prev) => ({ ...prev, age: e.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-[20px] leading-none text-slate-900 placeholder:text-slate-400 focus:border-emerald-500 focus:bg-white focus:outline-none"
                  placeholder="选填"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              className="mt-1 w-full rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-600 px-4 py-3.5 text-[18px] font-bold tracking-wide text-white shadow-[0_8px_20px_rgba(5,150,105,0.28)] transition hover:from-emerald-700 hover:to-teal-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitting ? "提交中..." : "提交登记"}
            </button>

            {!canSubmit && (
              <p className="text-center text-xs text-slate-500">请填写有效姓名和手机号后提交</p>
            )}
          </form>

          {successPatientId && (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-3.5 text-sm text-emerald-700">
              登记成功，您的患者编号：{successPatientId}。正在跳转到诊断分析页面...
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-3.5 text-sm text-rose-700">
              {error}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
