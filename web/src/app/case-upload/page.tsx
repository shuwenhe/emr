"use client";

import { ChangeEvent, FormEvent, useMemo, useState } from "react";
import mammoth from "mammoth";

type ImportResponse = {
  ok: boolean;
  message: string;
  new_ids?: string[];
  output?: string;
};

const DEFAULT_TEMPLATE = `一、病历概述
患者，男，66岁。左侧肋部灼痛2月余，夜间痛明显，VAS 7分，睡眠受影响。

二、诊断信息
临床诊断：带状疱疹后遗神经痛（肋间神经分布区）。

三、治疗过程
给予神经营养、镇痛方案与局部保护，结合睡眠管理与焦虑疏导。2周后夜间痛降至VAS 4分。

四、随访情况
建议2周复评疼痛和睡眠质量，1个月评估功能恢复；若疼痛反跳或出现新发神经体征，提前专科复诊。`;

function decodeByEncoding(buffer: ArrayBuffer, encoding: string): string {
  try {
    return new TextDecoder(encoding, { fatal: false }).decode(buffer);
  } catch {
    return "";
  }
}

function replacementRatio(text: string): number {
  if (!text) return 1;
  const replacements = (text.match(/\uFFFD/g) || []).length;
  return replacements / text.length;
}

async function parseImportFile(file: File): Promise<string> {
  const lowerName = file.name.toLowerCase();
  const mime = file.type.toLowerCase();
  const isDocx =
    lowerName.endsWith(".docx") ||
    mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

  if (isDocx) {
    const arrayBuffer = await file.arrayBuffer();
    const { value } = await mammoth.extractRawText({ arrayBuffer });
    return value;
  }

  const isPlainTextLike =
    lowerName.endsWith(".txt") ||
    lowerName.endsWith(".md") ||
    mime.startsWith("text/") ||
    mime === "";
  if (!isPlainTextLike) {
    if (lowerName.endsWith(".doc") || mime === "application/msword") {
      throw new Error("仅支持 .txt / .md / .docx 文件。如果上传的是 .doc 文件，请先转换成 .docx 文件");
    }
    throw new Error("仅支持 .txt / .md / .docx 文件");
  }

  const arrayBuffer = await file.arrayBuffer();
  const bytes = new Uint8Array(arrayBuffer);
  if (bytes.some((b) => b === 0)) {
    throw new Error("检测到二进制内容，请上传文本文件或 .docx");
  }

  const utf8 = decodeByEncoding(arrayBuffer, "utf-8");
  const gb18030 = decodeByEncoding(arrayBuffer, "gb18030");
  return replacementRatio(gb18030) < replacementRatio(utf8) ? gb18030 : utf8;
}

export default function CaseUploadPage() {
  const [sourceName, setSourceName] = useState("前端病例上传");
  const [content, setContent] = useState("");
  const [dryRun, setDryRun] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ImportResponse | null>(null);

  const canSubmit = useMemo(() => content.trim().length > 0 && !submitting, [content, submitting]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setResult(null);
    try {
      const text = await parseImportFile(file);
      setContent(text);
      setResult({ ok: true, message: `已读取文件：${file.name}` });
    } catch (error) {
      setResult({ ok: false, message: `读取文件失败：${String(error)}` });
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setResult(null);

    try {
      const response = await fetch("/api/kb/import-case", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          source_name: sourceName,
          case_text: content,
          dry_run: dryRun,
        }),
      });
      const payload = (await response.json().catch(() => ({}))) as ImportResponse;
      if (!response.ok) {
        setResult({
          ok: false,
          message: payload.message || `导入失败 (HTTP ${response.status})`,
          output: payload.output,
        });
        return;
      }
      setResult({
        ok: true,
        message: payload.message || "病例导入成功",
        new_ids: payload.new_ids,
        output: payload.output,
      });
      if (!dryRun) {
        setContent("");
      }
    } catch (error) {
      setResult({
        ok: false,
        message: `导入失败: ${String(error)}`,
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <header className="mb-6 rounded-2xl border border-slate-200 bg-gradient-to-r from-emerald-50 via-white to-cyan-50 p-5">
        <h1 className="text-2xl font-semibold text-slate-900">上传病例入库</h1>
        <p className="mt-2 text-sm text-slate-600">
          贴入病例原文后，系统将自动拆分为 3 条 KB 记录（模板、治疗、随访）并写入知识库。
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">来源名称</span>
            <input
              value={sourceName}
              onChange={(e) => setSourceName(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none"
              placeholder="例如：门诊病例导入"
              maxLength={80}
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-sm font-medium text-slate-700">从文件读取</span>
            <input
              type="file"
              accept=".txt,.md,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              onChange={handleFileChange}
              className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-md file:border-0 file:bg-emerald-600 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-emerald-700"
            />
          </label>
        </div>

        <label className="block">
          <span className="mb-1 block text-sm font-medium text-slate-700">病例原文</span>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={16}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-6 focus:border-emerald-500 focus:outline-none"
            placeholder="请粘贴病例原文"
          />
        </label>

        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
            />
            仅预览（dry-run，不写入）
          </label>

          <button
            type="button"
            onClick={() => setContent(DEFAULT_TEMPLATE)}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            填充示例模板
          </button>

          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {submitting ? "导入中..." : "上传并导入"}
          </button>
        </div>
      </form>

      {result && (
        <section className={`mt-5 rounded-xl border p-4 ${result.ok ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}>
          <h2 className={`text-sm font-semibold ${result.ok ? "text-emerald-800" : "text-rose-800"}`}>
            {result.ok ? "导入结果" : "错误信息"}
          </h2>
          <p className={`mt-1 text-sm ${result.ok ? "text-emerald-700" : "text-rose-700"}`}>{result.message}</p>
          {result.new_ids && result.new_ids.length > 0 && (
            <p className="mt-2 text-xs text-slate-700">新增 ID: {result.new_ids.join(", ")}</p>
          )}
          {result.output && (
            <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{result.output}</pre>
          )}
        </section>
      )}
    </main>
  );
}
