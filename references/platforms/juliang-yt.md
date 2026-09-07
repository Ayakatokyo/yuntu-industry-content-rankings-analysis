# 平台知识地图：巨量云图

本页用于把“巨量云图 / 行业灵感 / 行业内容榜 / 素材详情秒级拆解”路由到当前技能内部的两个固定连接器知识页。

## 连接器入口

- 列表：`references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_list.md`
- 详情：`references/connectors/juliang-yt/rpa_conn_juliang_yt_industry_content_rankings_details.md`

## 说明

- 平台固定为 `RPA_JULIANG_YT_ACCOUNT_PASSWORD`
- 不允许外部覆盖 `function_code`
- 当前技能在两个连接器结果之上增加了候选池补位、规范化、分析事实包和报告渲染
- 详情使用 `POST /adg/v1/agent/fetch/tasks` 提交及 `POST /adg/v1/agent/fetch/tasks/status` 查询；提交成功只表示获得 `task_group_id`，必须等终态文件或记录落盘。
