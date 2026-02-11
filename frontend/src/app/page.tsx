import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-50">
      <main className="flex min-h-screen w-full flex-col gap-10 px-10 py-16">
        <header className="space-y-4">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-blue-600">
            诊所医生端
          </p>
          <h1 className="text-4xl font-semibold text-slate-900">
            红外热成像诊断与病历管理平台
          </h1>
          <p className="max-w-2xl text-lg text-slate-600">
            支持自动生成电子病历、规范化存储与调取，并与诊断报告联动。
          </p>
        </header>

        <section className="grid gap-6 md:grid-cols-2">
          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-xl font-semibold text-slate-900">电子病历管理</h2>
            <p className="mt-2 text-slate-600">生成 EMR、查询病历与按患者检索。</p>
            <Link
              href="/emr"
              className="mt-6 inline-flex items-center rounded-full bg-blue-600 px-6 py-2 text-sm font-semibold text-white hover:bg-blue-700"
            >
              进入病历管理
            </Link>
          </div>

          <div className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
            <h2 className="text-xl font-semibold text-slate-900">诊断报告联动</h2>
            <p className="mt-2 text-slate-600">自动关联报告、治疗方案与医生意见。</p>
            <div className="mt-6 text-sm text-slate-500">
              后端接口：/emr/generate、/emr/{'{emr_id}'}、/emr
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
