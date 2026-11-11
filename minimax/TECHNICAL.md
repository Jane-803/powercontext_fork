# 一页技术说明

## 模块结构

`sdd_context` 是面向单个开发任务的上下文选择层。`corpus.py` 从 manifest 读取真实文件并计算 SHA-256；`database.py` 将内容、元数据和确定性向量写入 seekdb，并由 seekdb 执行向量查询；`service.py` 在候选结果上按 `logical_id + version + status` 选择当前有效版本；`powercontext_store.py` 通过 PowerContext 1.2.0 HTTP API 保存和恢复 Handoff；`minimax_agent.py` 将最终上下文交给 MiniMax API，并保存可核对但不含密钥的调用记录。

## 上下文选择

输入是自然语言开发任务。第一阶段由 seekdb 返回任务相关候选并记录候选 ID；第二阶段对同一逻辑资料只保留最高的 `current` 版本，排除 `superseded`。因此先导入 v1、再导入 v2 后，结果使用 `specs/place-filter-v2.md`，而不是固定答案。输出按 spec、code、test、decision 分类，每项包含仓库路径、版本、内容和数据库距离。

本题样例要求修改 `filter_places`：增加包含边界的最低评分过滤，阈值范围为 0..5。必须保留分类和距离过滤、负距离错误以及输入顺序。上下文中的必要来源为 `specs/place-filter-v2.md`、`snapshots/before/catalog.py`、`tests/test_catalog.py` 和 `docs/decision-ordering.md`。

## 三项技术分工

- **seekdb 1.4.0.post1**：持久化工程资料、向量和元数据；任务候选由实际 `Collection.query` 产生，而不是扫描内存或固定返回。
- **PowerContext 1.2.0**：将目标、已完成事项、待办、下一步和来源保存为 Handoff revision。新的 CLI 进程从 HTTP Server 读回状态，随后合入上下文。
- **MiniMax**：Anthropic-compatible `/v1/messages` 接口接收任务和检索上下文，生成并原子写入 `catalog.py`。调用记录包含 context digest、request ID、模型、token usage 及修改前后哈希，代码差异可与返回内容核对；无效响应不会修改目标文件。

## 有效性验证

完全相同的 `tests/test_catalog.py` 在旧快照上有 3 个目标失败，原因是尚无 `min_rating`；在最终实现上 5 项全部通过。回归测试覆盖原分类、距离、异常和顺序行为。`tests/test_context_selection.py` 与 `tests/test_service.py` 验证失效规格排除、v2 替换 v1、真实来源定位和恢复状态合入。日志记录命令、退出码和 stdout，不用缺依赖或修改断言制造“修改前失败”。
