#!/usr/bin/env python3
"""Fix KB JSONL: normalize categories and deduplicate IDs.

Replacements:
- category 'case_study' -> 'report_template'
- category 'diagnosis_criteria' -> 'interpretation_rule'

If an ID is duplicated, append a numeric suffix to make it unique.
"""

from pathlib import Path
import json

KB_PATH = Path(__file__).resolve().parents[1] / "rag" / "kb" / "knowledge_base.jsonl"
BACKUP_PATH = KB_PATH.with_suffix('.jsonl.bak')

def main():
    text = KB_PATH.read_text(encoding='utf-8')
    lines = [l for l in text.splitlines() if l.strip()]
    seen = {}
    out_lines = []
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            out_lines.append(line)
            continue

        # normalize categories
        cat = obj.get('category')
        if cat == 'case_study':
            obj['category'] = 'report_template'
        elif cat == 'diagnosis_criteria':
            obj['category'] = 'interpretation_rule'

        orig_id = str(obj.get('id') or '')
        new_id = orig_id
        if not new_id:
            # generate fallback id
            base = 'KB-IR-BG-UNKN'
            new_id = base

        if new_id in seen:
            seen[new_id] += 1
            new_id = f"{new_id}-dup{seen[new_id]}"
        else:
            seen[new_id] = 0

        obj['id'] = new_id
        out_lines.append(json.dumps(obj, ensure_ascii=False))

    # backup original
    KB_PATH.replace(BACKUP_PATH)
    # write fixed file
    KB_PATH.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
    print(f"Fixed KB written to: {KB_PATH}\nOriginal backed up at: {BACKUP_PATH}")

if __name__ == '__main__':
    main()
