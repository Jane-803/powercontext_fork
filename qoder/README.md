# PaperTrail · 研究资料雷达

PaperTrail 解决论文、笔记和实验资料散落后难以再次找到的问题。用户导入带标题、摘要、标签、年份和来源的资料，用自然语言搜索；seekdb 持久化资料和向量，并在数据库内执行语义检索及年份条件过滤。结果包含相似度、摘要与原始来源。

`site/` 是同一项目的展示与交互网站：部署到 Qoder Sites 后可直接体验内置样例；本地由 Python 服务托管时自动使用真实 seekdb API。

## 安装与启动

要求 Python 3.11+、pyseekdb 1.4.0.post1。嵌入式 seekdb 支持 Linux/macOS；Windows 请根据 `.env.example` 配置 seekdb Server。

```bash
cd qoder
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m papertrail.server --port 8787
```

打开 `http://127.0.0.1:8787`。启动时会将 `data/sample-papers.json` 中 6 篇公开论文资料 upsert 到 seekdb。

## 验证样例

输入：`long context retrieval quality`，起始年份 `2020`。

预期：结果不包含 2020 年以前论文；返回项包含标题、作者、年份、摘要、来源和相关度；API 的 `engine` 为 `seekdb vector search + structured year filter`。

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python scripts/verify.py
curl -X POST http://127.0.0.1:8787/api/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"long context retrieval quality","year_from":2020,"limit":3}' \
  | tee records/seekdb-e2e.json
```

前两个命令是不需要数据库的确定性预检；最后一条是在运行中服务上产生的真实 seekdb 查询记录。评审可以修改 query 和年份确认结果动态变化。

## seekdb 的实际作用

`PaperStore.upsert` 将摘要作为 document、论文属性作为 metadata、本地确定性向量作为 embedding 写入集合 `research_materials`。`PaperStore.search` 调用 `Collection.query`，传入 query embedding 与 `year >= year_from` 条件。服务不会把全部数据拉回 Python 后自行排序或过滤。

## Qoder 与 Qoder Sites

主要开发和发布必须在参赛者的真实 Qoder 个人账号中完成。源码提供了完整的可复现工程和记录模板，但模板不冒充 Qoder 证据。操作步骤：

1. 在 Qoder 打开包含本目录的仓库。
2. 使用 `records/qoder-development-template.md` 中的提示完成测试与一次迭代。
3. 保存 Qoder 的规划、实现、调试截图并记录 UID。
4. 在 Qoder Sites 选择 `qoder/site/` 创建站点，发布并设置“任何人都可访问”。
5. 无痕窗口验证 URL，将真实信息写入 `records/sites-publication.json` 和 `records/qoder-development.md`，再次提交。

当前环境未安装或登录 Qoder，因此仓库不包含伪造的 Qoder 对话或 Sites URL。没有真实 Qoder 记录和公开 Sites 地址时不要提交比赛平台。

## 目录

- `papertrail/`：seekdb 数据层、业务服务和 HTTP 服务
- `site/`：Qoder Sites 静态网站
- `data/`：公开论文演示数据及原始链接
- `tests/`：向量、导入、检索参数和边界测试
- `records/`：验证记录及 Qoder/Sites 留证模板

演示论文元数据来源于各条记录中的 arXiv 页面；本项目只整理公开标题、作者、摘要概述和链接，不包含论文全文。
