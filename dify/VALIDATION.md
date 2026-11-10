# 验证样例

## 双轮玩法

1. 确保 PowerContext 为空状态，在 Dify 中输入 `player_id=comet-7`、`era=恐龙时代`、`mischief=给每只恐龙发一个闹钟`。
2. 首轮输出应含四个固定栏目，`memory_state` 为 `first_meeting`，且不得伪造历史。
3. 保持 `player_id=comet-7`，改为 `era=古罗马`、`mischief=让元老院用恐龙叫声投票`。
4. 第二轮 `memory_state` 应为 `recalled`，NPC 应明确提到上轮“恐龙闹钟”并用它改变新剧情。
5. 换用 `player_id=quiet-2` 再运行，应恢复 `first_meeting`，证明玩家隔离。

## 无 Dify 的确定性预检

```bash
cd dify
python -m pip install -r requirements.txt
python -m pytest -q
python scripts/verify.py
```

`verify.py` 解析 DSL，启动本地 PowerContext 契约替身，执行空召回 -> 写入 -> 跨轮召回。结果写入
`records/validation.json`。该替身只用于预检；正式验收按 README 连接真实 PowerContext。

## 重置

- 真实 PowerContext：更换 `player_id`即可得到新 scope，不需要删除其他玩家记忆。
- 契约替身：删除传给 `--data` 的 JSON 文件。
