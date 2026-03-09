from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional, Tuple

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from .kb_utils import normalize_text, table_to_linearized_text, table_to_markdown


@dataclass
class Block:
    block_type: str
    text: str
    table_markdown: Optional[str]
    table_linearized_text: Optional[str]
    table_rows: Optional[List[List[str]]]
    title_path: List[str]


def _iter_block_items(parent: Document) -> Iterable[object]:
    body = parent.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _heading_level(paragraph: Paragraph) -> Optional[int]:
    style_name = (paragraph.style.name or "").strip()
    if not style_name.lower().startswith("heading"):
        return None
    level_str = "".join(ch for ch in style_name if ch.isdigit())
    if not level_str:
        return None
    level = int(level_str)
    if level <= 0:
        return None
    return level


def _update_title_path(title_path: List[str], paragraph: Paragraph) -> None:
    level = _heading_level(paragraph)
    if not level:
        return
    while len(title_path) < level:
        title_path.append("")
    title_path[level - 1] = normalize_text(paragraph.text)
    del title_path[level:]


def _extract_table(table: Table) -> List[List[str]]:
    rows: List[List[str]] = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            cell_text = normalize_text(cell.text)
            cells.append(cell_text)
        rows.append(cells)
    return rows


def docx_to_markdown(path: str) -> str:
    document = Document(path)
    lines: List[str] = []
    for block in _iter_block_items(document):
        if isinstance(block, Paragraph):
            text = normalize_text(block.text)
            if not text:
                continue
            level = _heading_level(block)
            if level:
                lines.append(f"{'#' * level} {text}")
            else:
                lines.append(text)
            lines.append("")
        elif isinstance(block, Table):
            rows = _extract_table(block)
            if not rows:
                continue
            table_markdown = table_to_markdown(rows)
            if table_markdown:
                lines.append(table_markdown)
                lines.append("")
    return "\n".join(lines).strip()


_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def _looks_like_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _parse_markdown_row(line: str) -> List[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells = [cell.strip().replace("\\|", "|") for cell in stripped.split("|")]
    return cells


def _parse_markdown_table(lines: List[str]) -> List[List[str]]:
    if len(lines) < 2:
        return []
    if not _TABLE_SEPARATOR_RE.match(lines[1]):
        return []
    rows = [_parse_markdown_row(lines[0])]
    for line in lines[2:]:
        rows.append(_parse_markdown_row(line))
    return rows


def parse_markdown(markdown: str) -> List[Block]:
    lines = markdown.splitlines()
    blocks: List[Block] = []
    title_path: List[str] = []
    buffer: List[str] = []

    def flush_paragraph() -> None:
        if not buffer:
            return
        text = normalize_text(" ".join(buffer))
        buffer.clear()
        if not text:
            return
        blocks.append(
            Block(
                block_type="paragraph",
                text=text,
                table_markdown=None,
                table_linearized_text=None,
                table_rows=None,
                title_path=title_path.copy(),
            )
        )

    idx = 0
    while idx < len(lines):
        line = lines[idx].rstrip()
        if not line.strip():
            flush_paragraph()
            idx += 1
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = normalize_text(stripped[level:].strip())
            if heading:
                while len(title_path) < level:
                    title_path.append("")
                title_path[level - 1] = heading
                del title_path[level:]
            idx += 1
            continue
        if _looks_like_table_line(line):
            flush_paragraph()
            table_lines = [line]
            idx += 1
            while idx < len(lines) and lines[idx].strip():
                if not _looks_like_table_line(lines[idx]):
                    break
                table_lines.append(lines[idx])
                idx += 1
            rows = _parse_markdown_table(table_lines)
            if rows:
                table_markdown = "\n".join(table_lines).strip()
                table_linearized = table_to_linearized_text(rows)
                blocks.append(
                    Block(
                        block_type="table",
                        text="",
                        table_markdown=table_markdown,
                        table_linearized_text=table_linearized,
                        table_rows=rows,
                        title_path=title_path.copy(),
                    )
                )
            continue
        buffer.append(line.strip())
        idx += 1

    flush_paragraph()
    return blocks


def parse_docx_with_markdown(path: str) -> Tuple[str, List[Block]]:
    markdown = docx_to_markdown(path)
    return markdown, parse_markdown(markdown)


def parse_docx(path: str) -> List[Block]:
    _, blocks = parse_docx_with_markdown(path)
    return blocks


def blocks_from_text(text: str) -> List[Block]:
    paragraphs: List[str] = []
    buffer: List[str] = []
    for line in text.splitlines():
        stripped = normalize_text(line)
        if not stripped:
            if buffer:
                paragraphs.append(" ".join(buffer).strip())
                buffer = []
            continue
        buffer.append(stripped)
    if buffer:
        paragraphs.append(" ".join(buffer).strip())

    blocks: List[Block] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        blocks.append(
            Block(
                block_type="paragraph",
                text=paragraph,
                table_markdown=None,
                table_linearized_text=None,
                table_rows=None,
                title_path=[],
            )
        )
    return blocks
