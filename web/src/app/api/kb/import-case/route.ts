import { mkdtemp, writeFile, unlink, access, rm, readFile, mkdir, rename } from "node:fs/promises";
import { constants as fsConstants, statSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { NextResponse } from "next/server";

const execFileAsync = promisify(execFile);

type UploadedCaseFileRecord = {
  file_hash: string;
  content_hash?: string;
  file_name: string;
  file_size: number | null;
  source_name: string;
  imported_at: string;
  new_ids: string[];
};

function resolveProjectRoot() {
  if (process.env.EMR_PROJECT_ROOT) {
    return process.env.EMR_PROJECT_ROOT;
  }

  const cwd = process.cwd();
  let current = cwd;
  for (let i = 0; i < 5; i++) {
    const scriptPath = path.join(current, "scripts", "import_case_to_kb.py");
    try {
      statSync(scriptPath);
      return current;
    } catch {
      const parent = path.dirname(current);
      if (parent === current) break;
      current = parent;
    }
  }

  if (cwd.includes("/.next/standalone")) {
    return path.resolve(cwd, "../..");
  }

  if (cwd.endsWith("/web") || cwd.includes("/web/.next")) {
    return path.resolve(cwd, "..");
  }

  return path.resolve(cwd, "..");
}

function resolveCaseImportRegistryPath(projectRoot: string) {
  if (process.env.EMR_CASE_IMPORT_REGISTRY?.trim()) {
    return process.env.EMR_CASE_IMPORT_REGISTRY.trim();
  }
  return path.resolve(projectRoot, "rag", "kb", "uploaded_case_files.json");
}

async function loadCaseImportRegistry(registryPath: string): Promise<UploadedCaseFileRecord[]> {
  try {
    const raw = await readFile(registryPath, "utf-8");
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is UploadedCaseFileRecord => {
      return Boolean(item && typeof item === "object" && typeof item.file_hash === "string" && item.file_hash.trim());
    });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

async function saveCaseImportRegistry(registryPath: string, records: UploadedCaseFileRecord[]) {
  await mkdir(path.dirname(registryPath), { recursive: true });
  const tempPath = `${registryPath}.tmp`;
  const payload = `${JSON.stringify(records, null, 2)}\n`;
  await writeFile(tempPath, payload, "utf-8");
  await rename(tempPath, registryPath);
}

function buildDuplicateMessage(record: UploadedCaseFileRecord) {
  const parts = [
    "该文件之前已经上传处理过了",
    record.file_name ? `文件名：${record.file_name}` : "",
    record.imported_at ? `处理时间：${record.imported_at}` : "",
    record.new_ids.length > 0 ? `已生成 ID：${record.new_ids.join(", ")}` : "",
  ].filter(Boolean);
  return parts.join("\n");
}

function normalizeCaseText(text: string) {
  return text.replace(/\r\n/g, "\n").trim();
}

function computeCaseTextHash(text: string) {
  return createHash("sha256").update(normalizeCaseText(text), "utf-8").digest("hex");
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
      file_hash?: string;
      file_name?: string;
      file_size?: number;
    };

    const caseText = String(payload.case_text || "").trim();
    const sourceName = String(payload.source_name || "前端病例上传").trim().slice(0, 80);
    const dryRun = Boolean(payload.dry_run);
    const fileHash = String(payload.file_hash || "").trim().toLowerCase();
    const fileName = String(payload.file_name || "").trim().slice(0, 255);
    const fileSize = typeof payload.file_size === "number" && Number.isFinite(payload.file_size) ? payload.file_size : null;

    if (!caseText) {
      return NextResponse.json({ message: "病例内容不能为空" }, { status: 400 });
    }

    const projectRoot = resolveProjectRoot();
    const contentHash = computeCaseTextHash(caseText);
    const registryPath = resolveCaseImportRegistryPath(projectRoot);
    const caseImportRegistry = await loadCaseImportRegistry(registryPath);

    if (fileHash || contentHash) {
      const existingRecord = caseImportRegistry.find((record) => {
        if (fileHash && record.file_hash === fileHash) {
          return true;
        }
        if (record.content_hash && record.content_hash === contentHash) {
          return true;
        }
        return false;
      });
      if (existingRecord) {
        return NextResponse.json(
          {
            ok: false,
            message: "该文件之前已经上传处理过了",
            output: buildDuplicateMessage(existingRecord),
          },
          { status: 409 }
        );
      }
    }

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

      let output = [stdout, stderr].filter(Boolean).join("\n").trim();
      const newIds = parseNewIds(output);

      if (!dryRun) {
        try {
          caseImportRegistry.push({
            file_hash: fileHash,
            content_hash: contentHash,
            file_name: fileName || "未命名文件",
            file_size: fileSize,
            source_name: sourceName || "前端病例上传",
            imported_at: new Date().toISOString(),
            new_ids: newIds,
          });
          await saveCaseImportRegistry(registryPath, caseImportRegistry);
        } catch (registryError) {
          output = [output, `[WARN] duplicate registry update failed: ${String(registryError)}`]
            .filter(Boolean)
            .join("\n");
        }
      }

      return NextResponse.json({
        ok: true,
        message: dryRun ? "dry-run 成功，已生成 3 条预览记录" : "病例导入成功",
        new_ids: newIds,
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
      await rm(tmpDir, { recursive: true, force: true }).catch(() => undefined);
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
