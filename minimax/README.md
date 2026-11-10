# 规有所依：SDD 工程上下文模块

本目录是可独立运行的比赛交付物。它将规格、代码、测试和设计决策写入 seekdb，按开发任务检索候选资料，过滤掉失效版本，并把 PowerContext Handoff 状态合并进开发上下文。随后可把该上下文交给 MiniMax 完成真实代码修改。

验证任务是：为地点过滤函数增加 `min_rating`，拒绝 0..5 之外的阈值；已有分类、最大距离、异常处理和输入顺序必须保持。

## 环境

- Python 3.11+
- PowerContext 1.2.0
- pyseekdb 1.4.0.post1
- MiniMax Anthropic-compatible API，默认 `MiniMax-M2.1`
- Linux/macOS 可直接使用嵌入式 seekdb；Windows 使用 `SEEKDB_*` 连接 seekdb Server

```bash
cd minimax
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env                 # 填入 MiniMax Key；不要提交
```

Windows 激活命令为 `.venv\Scripts\Activate.ps1`。Windows 不使用嵌入式 pyseekdb，请按 `.env.example` 配置 seekdb Server。

## 一次完整验收

1. 创建基础 PowerContext 配置并启动服务：

```bash
powercontext config init --template --output .runtime/powercontext.env
powercontext server run --env-file .runtime/powercontext.env
```

2. 新终端加载 `.env`，执行上下文验收。该脚本先导入 v1，再导入 v2；输出必须只使用 v2，并包含真实代码、测试来源及重启后读回的任务状态：

```bash
python scripts/verify_context.py
```

脚本产生 `records/context.json` 和 `records/context_run.json`。前者明确列出数据库查询候选 ID、有效规格、代码文件、测试文件、设计决策以及 PowerContext Handoff revision。

3. 用 MiniMax 参与修改并自动留证：

```bash
python -m sdd_context.cli --root . run-minimax \
  --context records/context.json --output records/minimax_run.json
```

`records/minimax_run.json` 保存供应商、模型、请求 ID、用量、任务、上下文摘要和模型返回代码，不保存 Key 或私有思维链。将返回代码应用到 `sample_app/catalog.py`；本提交中的最终文件就是该目标结果。没有真实 Token 时命令会明确失败，不会生成伪记录。

4. 对同一组测试执行修改前后验证：

```bash
python scripts/verify_tests.py
python -m pytest -q
```

预期 `verify_tests.py` 输出 `before_exit: 1`、`after_exit: 0`。旧快照的失败是目标功能缺失导致的 `unexpected keyword argument 'min_rating'`，不是环境错误。完整 stdout、退出码和命令写入 `records/test_run.json`，代码差异见 `CODE_DIFF.md`。

5. 保存完成状态并模拟模块重启后读取：

```bash
python -m sdd_context.cli --root . save-state fixtures/state-complete.json
python -m sdd_context.cli --root . load-state
python -m sdd_context.cli --root . context --output records/resumed-context.json
```

最后一个命令创建全新的进程，并将已完成事项、待办和验证状态用于新上下文。

## CLI 输入与输出

| 命令 | 输入 | 输出 |
| --- | --- | --- |
| `ingest MANIFEST` | 路径、类型、逻辑 ID、版本和状态 | 写入 seekdb 的数量 |
| `context --task TEXT` | 自然语言任务 | 有效规格、相关代码/测试/决策、DB 查询证据和任务状态 |
| `save-state FILE` | 目标、完成项、待办和下一步 | PowerContext Scope、Handoff ID 与 revision |
| `load-state` | 固定样例 Scope | PowerContext 中的当前 Handoff |
| `run-minimax` | 任务与上下文 JSON | MiniMax 调用证据和返回代码 |

## 重置

停止 PowerContext Server，删除 `.runtime/` 后重新运行上述步骤。远程 seekdb 模式下删除集合 `engineering_context`，或改用全新的测试数据库。`POWERCONTEXT_SCOPE_KEY` 改成新值可创建新的空任务 Scope。

已知限制：本样例用确定性本地特征哈希生成检索向量，重点验证资料版本和来源选择；它不替代通用代码 embedding 模型。MiniMax 调用需要参赛者自己的 Token Plan。
