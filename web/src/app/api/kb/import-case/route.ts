import { mkdtemp, writeFile, unlink, access } from "node:fs/promises";
import { constants as fsConstants } from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { NextResponse } from "next/server";

const execFileAsync = promisify(execFile);

function resolveProjectRoot() {
  return path.resolve(process.cwd(), "..");
}

async function resolvePythonBinary(projectRoot: string) {
  const candidates = [
    process.env.KB_PYTHON?.trim() || "",
    process.env.PYTHON_BIN?.trim() || "",
    path.resolve(os.homedir(), ".venv", "bin", "python"),
    path.resolve(projectRoot, ".venv", "bin", "python"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    try {
      await access(candidate, fsConstants.X_OK);
      return candidate;
    } catch {
      continue;
    }
  }
  return "python3";
}

function parseNewIds(output: string): string[] {
  const line = output
    .split(/\r?\n/)
    .find((entry) => entry.trim().toLowerCase().startsWith("[ok] new ids:"));
  if (!line) return [];
  const body = line.split(":", 2)[1] || "";
  return body
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export async function POST(request: Request) {
  try {
    const payload = (await request.json().catch(() => ({}))) as {
      case_text?: string;
      source_name?: string;
      dry_run?: boolean;
    };

    const caseText = String(payload.case_text || "").trim();
    const sourceName = String(payload.source_name || "前端病例上传").trim().slice(0, 80);
    const dryRun = Boolean(payload.dry_run);

    if (!caseText) {
      return NextResponse.json({ message: "病例内容不能为空" }, { status: 400 });
    }

    const projectRoot = resolveProjectRoot();
    const pythonBin = await resolvePythonBinary(projectRoot);
    const tmpDir = await mkdtemp(path.join(os.tmpdir(), "emr-case-import-"));
    const caseFile = path.join(tmpDir, "incoming_case.txt");

    await writeFile(caseFile, caseText, "utf-8");

    const args = [
      path.resolve(projectRoot, "scripts", "import_case_to_kb.py"),
      "--case-file",
      caseFile,
      "--kb-jsonl",
      path.resolve(projectRoot, "rag", "kb", "knowledge_base.jsonl"),
      "--kb-json",
      path.resolve(projectRoot, "rag", "kb", "knowledge_base.json"),
      "--source-name",
      sourceName || "前端病例上传",
    ];

    if (dryRun) {
      args.push("--dry-run");
    }

    try {
      const { stdout, stderr } = await execFileAsync(pythonBin, args, {
        cwd: projectRoot,
        timeout: 120000,
        maxBuffer: 1024 * 1024,
      });

      const output = [stdout, stderr].filter(Boolean).join("\n").trim();
      return NextResponse.json({
        ok: true,
        message: dryRun ? "dry-run 成功，已生成 3 条预览记录" : "病例导入成功",
        new_ids: parseNewIds(output),
        output,
      });
    } catch (error) {
      const stderr = (error as { stderr?: string })?.stderr || "";
      const stdout = (error as { stdout?: string })?.stdout || "";
      const output = [stdout, stderr].filter(Boolean).join("\n").trim();
      return NextResponse.json(
        {
          ok: false,
          message: "病例导入失败，请检查病例格式或服务日志",
          output,
        },
        { status: 500 }
      );
    } finally {
      await unlink(caseFile).catch(() => undefined);
    }
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        message: `请求处理失败: ${String(error)}`,
      },
      { status: 500 }
    );
  }
}
