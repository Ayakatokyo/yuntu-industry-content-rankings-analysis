# 云图 TOP6 严格批次真实报告重建设计

## 目标

基于 `yuntu-rankings-analysis-20260730-20260805-food-beverage-brands-top6-strict`
批次已落盘的真实 RPA 数据、详情数据、高光帧和已绑定来源的分析回执，重新生成正式报告，直接覆盖该批次的 `final-report` 目录。

## 已确认的输入边界

- 榜单事实：`normalized/list-records.json`，共 1,000 条真实 RPA 榜单记录。
- 素材详情：`normalized/detail-records/` 中 5 条 TOP 素材详情记录。
- 高光证据：`highlights-manifest.json` 和 `highlights/` 中 29 张可用截图。
- 分析解释：`diagnostic-analysis/yuntu-ai-analysis.json`。
- 来源绑定：`diagnostic-analysis/yuntu-ai-analysis.provenance.json`，其中记录分析 JSON、事实包和提示词的 SHA-256。

不得重跑 RPA，不得手改事实、指标、素材观察或 AI 结论，不得从截图补写未出现在分析回执中的结论。

## 重建链路

```text
真实 RPA 榜单 + 5 条详情 + 29 张高光帧
                + 已绑定的事实包 / 分析回执
                              |
                              v
             rpa_connector.py render-report
                              |
                              v
      final-report/{final-report.html, final-report.md,
                   final-report-data.json, presentation-report.json, assets/}
```

唯一允许写入报告的操作是既有 `render-report` 命令。输出目标为批次中的既有 `final-report`，按用户授权直接覆盖；渲染器的 `--highlight-asset-root` 显式指向当前批次根目录，使 HTML 只引用当前批次落盘的高光截图。

## 验收

1. 渲染命令成功，HTML、Markdown 和 JSON 产物非空。
2. 输出中的分析、事实包与 provenance 哈希仍和输入一致。
3. 29 张高光帧均可解析、均从当前批次复制，HTML 不存在缺失的本地图片引用。
4. 执行报告相关单测与结构化 HTML 检查。
5. 在浏览器进行桌面端目视检查，重点检查首屏、洞察图表、高光帧网格和单素材深度分析页面的溢出、空白与失效图片。

## 失败处理

如 provenance、输入契约、图片复制或渲染校验失败，停止交付并保留失败证据；不以手工编辑 HTML 或生成替代结论的方式绕过失败。
