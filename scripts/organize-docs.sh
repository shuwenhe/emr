#!/bin/bash
#
# 文档组织脚本
# 用于将AI分析相关的MD文档移动到 docs/ai-analysis/ 目录
#
# 使用方法：
#   ./organize-docs.sh
#
# 或者在项目根目录执行：
#   bash scripts/organize-docs.sh
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$PROJECT_ROOT/docs/ai-analysis"

echo "📚 文档组织工具"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 创建目标目录
mkdir -p "$DOCS_DIR"
echo "✓ 确保目录存在: $DOCS_DIR"

# 定义需要移动的文档模式
AI_DOC_PATTERNS=(
    "*AI*.md"
    "*ANALYSIS*.md"
    "*FLOWCHART*.md"
    "README_AI_*.md"
)

# 统计变量
moved_count=0
skipped_count=0

cd "$PROJECT_ROOT"

# 移动匹配的文件
for pattern in "${AI_DOC_PATTERNS[@]}"; do
    for file in $pattern 2>/dev/null; do
        # 跳过如果文件不存在或已在目标目录
        if [[ ! -f "$file" ]] || [[ "$file" == "docs/"* ]]; then
            continue
        fi
        
        # 跳过主README
        if [[ "$file" == "README.md" ]]; then
            skipped_count=$((skipped_count + 1))
            continue
        fi
        
        echo "  → 移动: $file"
        mv "$file" "$DOCS_DIR/"
        moved_count=$((moved_count + 1))
    done
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 完成！"
echo "   移动文件: $moved_count 个"
echo "   跳过文件: $skipped_count 个"
echo "   目标目录: $DOCS_DIR"
echo ""
echo "📖 查看文档："
echo "   cd docs/ai-analysis && ls -lh"
echo ""
