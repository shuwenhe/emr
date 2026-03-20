# Case Import Template (Paste Raw Case Here)

Use this template when adding one real case.
Then run:

```bash
make kb-import-case KB_CASE_IMPORT_FILE=rag/kb/incoming_case.txt
```

You can keep free text style. The parser prefers these section titles:
- 一、病历概述
- 二、诊断信息
- 三、治疗过程
- 四、随访情况

Example content for `rag/kb/incoming_case.txt`:

```text
一、病历概述
患者，男，66岁。左侧肋部灼痛2月余，夜间痛明显，VAS 7分，睡眠受影响。

二、诊断信息
临床诊断：带状疱疹后遗神经痛（肋间神经分布区）。

三、治疗过程
给予神经营养、镇痛方案与局部保护，结合睡眠管理与焦虑疏导。2周后夜间痛降至VAS 4分。

四、随访情况
建议2周复评疼痛和睡眠质量，1个月评估功能恢复；若疼痛反跳或出现新发神经体征，提前专科复诊。
```

Notes:
- One case import creates 3 KB rows automatically: report template, treatment guideline, follow-up rule.
- IDs are auto-generated and deduplicated.
- After import, `knowledge_base.json` is synced automatically.
