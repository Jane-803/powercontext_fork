# 验收清单

| 验收项 | 核对方式 |
| --- | --- |
| 项目可运行 | 按 README 安装并启动，浏览器搜索返回结果 |
| seekdb 实际参与 | 检查 `/api/search` 的 engine、`records/seekdb-e2e.json` 与 `PaperStore.search` |
| 结果真实 | 每条演示数据包含 arXiv 来源链接，搜索结果保持来源 |
| Qoder 主要开发 | 核对真实 UID、对话/任务截图、改动时间与 Git diff |
| Qoder Sites | 未登录/无痕打开公开 URL，核对站点内容和仓库链接 |

提交前必须将 `records/*-template.*` 替换或补充为真实证据。截图不得包含 API Key、密码、邮箱等隐私信息。
