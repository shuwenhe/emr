from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, Response

from route import reports


def test_resolve_source_doc_path_supports_explicit_file(monkeypatch, tmp_path: Path):
    source_file = tmp_path / "sample-source.docx"
    source_file.write_bytes(b"docx-placeholder")

    monkeypatch.setenv("RAG_SOURCE_ROOT", str(tmp_path))

    resolved = reports._resolve_source_doc_path("sample-source.docx")

    assert resolved == source_file.resolve()


def test_download_source_file_returns_kb_preview_for_title_only() -> None:
    response = reports.download_source_file("院内门诊随访建议单", inline=True)

    assert isinstance(response, Response)
    assert not isinstance(response, FileResponse)
    assert response.media_type == "text/plain; charset=utf-8"
    body = response.body.decode("utf-8")
    assert "来源标题: 院内门诊随访建议单" in body
    assert "知识库中同来源条目的汇总预览" in body
    assert "KB-HT-004" in body
    assert "高温异常区域处理建议" in body


def test_download_source_file_raises_when_source_missing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        reports.download_source_file("不存在的来源标题", inline=True)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "source_file_not_found"