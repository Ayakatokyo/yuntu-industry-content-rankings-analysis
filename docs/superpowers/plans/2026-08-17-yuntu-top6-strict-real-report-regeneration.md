# 云图 TOP6 严格批次真实报告重建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用已落盘、来源可验证的真实 RPA 数据与高光截图，直接覆盖指定 TOP6 严格批次的最终报告并完成可审计验收。

**Architecture:** 仅调用既有 `scripts/rpa_connector.py render-report`，把已绑定的分析 JSON、事实包和 provenance 传入渲染器。渲染器从同一批次的 `highlights/` 复制图片资产，重写 `final-report`，随后用 JSON、HTML 和浏览器验收链路确认输出的事实和资源完整性。

**Tech Stack:** Python 3、现有云图报告渲染器、JSON/JQ、HTML 静态检查、浏览器桌面端目视检查。

---

### Task 1: 锁定真实输入与覆盖目标

**Files:**
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/normalized/list-records.json`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.provenance.json`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/highlights-manifest.json`
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/`

- [ ] **Step 1: 验证输入规模和来源绑定**

Run:

```bash
jq 'length' 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/normalized/list-records.json'
jq '.artifacts' 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.provenance.json'
find 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/highlights' -name '*.jpg' | wc -l
```

Expected: 分别为 `1000`、含 analysis/factPack/prompt SHA-256 的 provenance 对象、`29`。

- [ ] **Step 2: 对渲染输入执行哈希校验**

Run:

```bash
cd 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis'
shasum -a 256 yuntu-ai-analysis.json yuntu-analysis-data.json yuntu-analysis-prompt.md
```

Expected: 三个 SHA-256 分别匹配 provenance 的 `analysisJson`、`factPack` 和 `prompt`。

### Task 2: 使用正式链路覆盖最终报告

**Files:**
- Read: `scripts/rpa_connector.py:768-780`
- Read: `scripts/yuntu_report.py:1269-1360`
- Modify: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/`

- [ ] **Step 1: 执行正式报告渲染命令**

Run:

```bash
python scripts/rpa_connector.py render-report \
  --analysis-json 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.json' \
  --fact-pack-json 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-analysis-data.json' \
  --analysis-provenance 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/diagnostic-analysis/yuntu-ai-analysis.provenance.json' \
  --output-dir 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report' \
  --highlight-asset-root 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict'
```

Expected: 命令退出码为 0，并写出 `final-report.html`、`final-report.md`、`final-report-data.json` 与 `presentation-report.json`。

- [ ] **Step 2: 检查报告主文件非空**

Run:

```bash
find 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report' \
  -maxdepth 1 -type f \( -name 'final-report.html' -o -name 'final-report.md' -o -name 'final-report-data.json' -o -name 'presentation-report.json' \) \
  -size +0c -print
```

Expected: 输出四个非空文件。

### Task 3: 验证报告事实、图片资产和页面结构

**Files:**
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report-data.json`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html`
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/assets/highlight-frames/`

- [ ] **Step 1: 校验输出中的事实规模和高光帧可用性**

Run:

```bash
jq '{status, highlightCount:(.highlightFrames | length), availableCount:([.highlightFrames[] | select(.available == true)] | length), chapters:(.presentation.chapters | keys)}' \
  'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report-data.json'
find 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/assets/highlight-frames' -name '*.jpg' | wc -l
```

Expected: `status` 为 `complete`，总数和可用数均为 `29`，图片数量为 `29`，章节包含 `chapter01`、`chapter02`、`chapter04`、`chapter05`。

- [ ] **Step 2: 检查本地图片引用不存在缺失文件**

Run:

```bash
node - <<'NODE'
const fs = require('fs');
const path = require('path');
const root = 'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report';
const html = fs.readFileSync(path.join(root, 'final-report.html'), 'utf8');
const refs = [...html.matchAll(/(?:src|href)=["']([^"']+)["']/g)].map((m) => m[1]).filter((ref) => ref.startsWith('assets/'));
const missing = refs.filter((ref) => !fs.existsSync(path.join(root, ref)));
if (missing.length) throw new Error(`missing local assets: ${missing.join(', ')}`);
console.log(`verified ${refs.length} local asset references`);
NODE
```

Expected: 输出已验证的本地资源引用数量，且进程退出码为 0。

- [ ] **Step 3: 运行报告回归测试**

Run:

```bash
python -m unittest tests.test_yuntu_report tests.test_yuntu_highlights -q
```

Expected: `OK`。

### Task 4: 桌面端视觉验收

**Files:**
- Read: `RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html`

- [ ] **Step 1: 在浏览器打开最终 HTML 并检查四个关键区域**

Inspect: 首屏报告元信息、02 章图表与标签、04 章高光帧网格、05 章单素材深度分析。

Expected: 无空白主内容、文本重叠、溢出、缺失图片或失效图表；高光帧及单素材模块正常显示。

- [ ] **Step 2: 记录最终哈希和验收结果**

Run:

```bash
shasum -a 256 \
  'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report.html' \
  'RPA数据汇总/yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict/final-report/final-report-data.json'
```

Expected: 为覆盖后的最终 HTML 和数据文件输出可追溯 SHA-256。
