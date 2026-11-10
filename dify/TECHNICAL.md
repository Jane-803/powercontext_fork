# 一页技术说明

**Timeline Grudge** 是一个会记仇的时空海关 NPC。玩家提交目的地和恶作剧，Chronos 给出剧情、
吐槽、混乱值和后续选项。同一 `player_id` 再次进入时，NPC 会引用真实旧棒改写新剧情。

**Dify 编排**：Workflow 依次执行玩家 scope 解析、历史召回、结果解析、LLM 叙事、记忆写回和结果输出。
LLM 提示词把历史标记为不可信数据，空召回时必须说明首次见面，防止伪造记忆。

**PowerContext 记忆**：`/v1/scopes` 用 `timeline-grudge-{player_id}` 幂等键建立隔离边界；
`/v1/context/prepare` 为当前请求准备最多 3000 bytes 历史；`/v1/memory/remember` 在成功叙事后保存玩家选择与结果。
scope 由可信工作流选择，不由模型输出决定。

**可复现性**：仓库提供 DSL、环境变量样例、真实 PowerContext 启动步骤、兼容三个必需端点的本地契约替身、
单元测试和双轮验证日志。契约替身不冒充 PowerContext，只让评审在没有模型凭据时预检 DSL 数据流。
