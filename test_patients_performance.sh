#!/bin/bash

# 性能测试脚本：患者列表API

API_BASE="http://127.0.0.1:8000"

echo "🔍 EMR 患者列表 API 性能测试"
echo "================================"
echo ""

# 等待后端启动
echo "⏳ 等待后端启动..."
for i in {1..30}; do
  if curl -m 1 -s "$API_BASE/health" > /dev/null 2>&1; then
    echo "✅ 后端已启动"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "❌ 后端启动超时，请执行: make service"
    exit 1
  fi
  sleep 1
done

echo ""
echo "📊 测试1: 获取第1页患者（30条）"
echo "---------------------------------------"
time curl -w "\nHTTP %{http_code} | Total: %{time_total}s | DNS: %{time_namelookup}s | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s\n" \
  -s -o /tmp/patients_p1.json \
  "$API_BASE/patients?page=1&limit=30"

echo ""
echo "📊 测试2: 获取第2页患者（30条）"
echo "---------------------------------------"
time curl -w "\nHTTP %{http_code} | Total: %{time_total}s | DNS: %{time_namelookup}s | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s\n" \
  -s -o /tmp/patients_p2.json \
  "$API_BASE/patients?page=2&limit=30"

echo ""
echo "📊 测试3: 获取第5页患者（30条）"
echo "---------------------------------------"
time curl -w "\nHTTP %{http_code} | Total: %{time_total}s | DNS: %{time_namelookup}s | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s\n" \
  -s -o /tmp/patients_p5.json \
  "$API_BASE/patients?page=5&limit=30"

echo ""
echo "📊 测试4: 包含归档患者的查询"
echo "---------------------------------------"
time curl -w "\nHTTP %{http_code} | Total: %{time_total}s | DNS: %{time_namelookup}s | Connect: %{time_connect}s | TTFB: %{time_starttransfer}s\n" \
  -s -o /tmp/patients_archived.json \
  "$API_BASE/patients?page=1&limit=30&include_archived=true"

echo ""
echo "📏 响应数据大小"
echo "---------------------------------------"
echo "Page 1: $(wc -c < /tmp/patients_p1.json | numfmt --to=iec-i --suffix=B 2>/dev/null || wc -c < /tmp/patients_p1.json) bytes"
echo "Page 2: $(wc -c < /tmp/patients_p2.json | numfmt --to=iec-i --suffix=B 2>/dev/null || wc -c < /tmp/patients_p2.json) bytes"
echo "Page 5: $(wc -c < /tmp/patients_p5.json | numfmt --to=iec-i --suffix=B 2>/dev/null || wc -c < /tmp/patients_p5.json) bytes"

echo ""
echo "✅ 性能测试完成"
echo ""
echo "💡 优化建议:"
echo "   • 前端缓存患者列表（使用 useMemo + React.memo）"
echo "   • 实现虚拟滚动用于超大数据集（>1000患者）"
echo "   • 前端搜索应该防抖并节流请求"
echo ""
