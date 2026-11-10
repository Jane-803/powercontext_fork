# Timeline Grudge: 记仇的时空 NPC

玩家向时空海关官 Chronos 提交一个历史恶作剧。它会记住每个玩家的旧棒，下一轮用旧恶作剧改变新的时间线。

## 技术分工

- **Dify 1.9+**：导入 `app.yml`，负责输入、HTTP 调用、记忆分支、LLM 叙事和输出。
- **PowerContext master**：负责玩家 scope、跨轮记忆写入和有界召回。接口与官方 `openapi/powercontext.yaml` 对齐。
- **模型**：DSL 默认 OpenAI `gpt-4o-mini`，导入后可在 LLM 节点换成评审环境中的任意聊天模型。

## 1. 启动真实 PowerContext

需要 Python 3.11+、Git 和 `uv`：

```bash
uv tool install --force "powercontext[cli,server] @ git+https://github.com/oceanbase/powercontext.git@master"
powercontext server run
curl http://127.0.0.1:8000/health/live
```

默认本地模式使用 SQLite，显式 Memory 不需要 inference provider。生产环境建议开启鉴权并设置
`POWERCONTEXT_TOKEN`。

## 2. 导入 Dify

1. 在 Dify 工作区选择“从 DSL 文件导入”，上传 `app.yml`。
2. 在环境变量中设置 `POWERCONTEXT_URL`。Dify 使用 Docker 而 PowerContext 运行在宿主机时，Windows/macOS 通常为
   `http://host.docker.internal:8000`；Linux 请使用可从 Dify 容器访问的宿主地址。
3. 如开启 PowerContext 鉴权，将 `POWERCONTEXT_TOKEN` 设为 secret；未开启时留空。
4. 打开 `Chronos narrates` 节点，绑定一个可用聊天模型并配置对应密钥。
5. 发布 Workflow，按 [VALIDATION.md](VALIDATION.md) 执行两轮样例。

## 3. 无 PowerContext 安装的 DSL 排练

`scripts/mock_powercontext.py` 只实现本应用所需的三个官方端点，数据持久化到 JSON：

```bash
cd dify
python scripts/mock_powercontext.py --port 18000 --data records/mock-memory.json
```

将 Dify 的 `POWERCONTEXT_URL` 设为该服务的可访问地址。正式验收应使用真实 PowerContext；契约替身用于离线演示和故障排查。

## 4. 自动预检

```bash
cd dify
python -m pip install -r requirements.txt pytest
python -m pytest -q
python scripts/verify.py
```

预检会验证 DSL 关键节点、玩家隔离、幂等 scope、记忆持久化和第二轮召回，并生成
`records/validation.json`。

## 已知限制

- Dify 的 HTTP Request 节点必须能访问 PowerContext；`127.0.0.1` 在容器中指向容器自身。
- 记忆是按用户输入的 `player_id` 隔离的游戏记录，不应存入真实姓名或敏感信息。
- DSL 不包含模型 API Key、PowerContext token 或预置私人记忆。

PowerContext 官方参考：<https://powercontext.oceanbase.io/zh/docs/develop/api-quickstart/>
