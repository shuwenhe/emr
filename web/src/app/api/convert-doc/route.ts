import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { NextResponse } from "next/server";
import mammoth from "mammoth";

const execFileAsync = promisify(execFile);

export async function POST(request: Request) {
  let tmpDir: string | null = null;

  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json(
        { error: "没有提供文件" },
        { status: 400 }
      );
    }

    const fileName = file.name.toLowerCase();
    const ext = path.extname(fileName);

    // 只处理 .doc 文件（不是 .docx）
    if (ext !== ".doc" || fileName.endsWith(".docx")) {
      return NextResponse.json(
        { error: "仅支持转换 .doc 文件（不支持 .docx）" },
        { status: 400 }
      );
    }

    tmpDir = await mkdtemp(path.join(os.tmpdir(), "doc-convert-"));
    const inputPath = path.join(tmpDir, `input.doc`);
    const inputBuffer = await file.arrayBuffer();

    // 写入上传的 .doc 文件
    await writeFile(inputPath, new Uint8Array(inputBuffer));

    // 使用 LibreOffice 转换为 .docx
    try {
      await execFileAsync("libreoffice", [
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        tmpDir,
        inputPath,
      ], {
        timeout: 30000,
      });
    } catch (error) {
      console.error("LibreOffice conversion error:", error);
      return NextResponse.json(
        { error: "文件转换失败，请检查文件格式是否正确" },
        { status: 500 }
      );
    }

    // 读取转换后的 .docx 文件
    const outputPath = path.join(tmpDir, "input.docx");
    const docxBuffer = await readFile(outputPath);

    // 使用 mammoth 提取文本
    try {
      const { value } = await mammoth.extractRawText({
        arrayBuffer: docxBuffer.buffer.slice(
          docxBuffer.byteOffset,
          docxBuffer.byteOffset + docxBuffer.byteLength
        ),
      });

      return NextResponse.json({
        text: value,
        message: "成功转换 .doc 文件",
      });
    } catch (error) {
      console.error("Text extraction error:", error);
      return NextResponse.json(
        { error: "无法从转换后的文件中提取文本" },
        { status: 500 }
      );
    }
  } catch (error) {
    console.error("Conversion error:", error);
    return NextResponse.json(
      { error: `转换失败: ${String(error)}` },
      { status: 500 }
    );
  } finally {
    // 清理临时文件
    if (tmpDir) {
      try {
        await rm(tmpDir, { recursive: true });
      } catch {
        // 忽略清理错误
      }
    }
  }
}
