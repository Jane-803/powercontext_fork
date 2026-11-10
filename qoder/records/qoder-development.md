# Qoder 开发记录

日期：2026-11-10
范围：`qoder/` 目录内的 PaperTrail
执行环境：Windows，Python 3.11.5，位于 `qoder-research-radar` 工作树

## 审查发现

搜索 API 和资料导入都直接消费外部输入，但缺少边界校验：

- POST 请求体是合法 JSON 但不是对象（如 `[]`）时，`service.search` 收到列表并触发 `AttributeError`，服务返回 500；
- `limit: null` 或非数字字符串触发 `TypeError`/`ValueError`，部分情况变成 500；
- `year_from` 接受布尔值和浮点数，分别被静默转成 `1` 和截断年份；
- `Content-Length` 缺失、为负或非数字时没有明确响应，超大请求体也没有上限；
- 导入文件只检查字段是否存在，`year`、`tags`、`status` 类型错误以及重复 `id` 会拖到 seekdb 写入阶段才失败，错误信息缺少论文序号和字段名。

这些问题会让客户端错误表现为服务端故障，并让前端把真实错误误判为“演示数据”。

## 修改内容

### `papertrail/service.py`

- 新增 `_parse_integer` / `_optional_integer`，统一接受整数和数字字符串，拒绝布尔值、浮点数及非数字文本；`limit: null` 和 `year_from: null` 仍按默认值处理。
- 新增 `_require_text`，要求 `id`、`title`、`authors`、`abstract`、`source` 为非空字符串。
- `import_file` 现在校验：根节点必须是对象、`papers` 必须是列表、每篇论文必须是对象、必填字段、`year` 类型、`tags` 必须是字符串列表、`status` 必须是字符串、`id` 不得重复；JSON 语法错误会带上文件名。所有论文通过校验后才写入，避免半批导入。
- `search` 现在拒绝非字符串 `query`、非整数 `limit`/`year_from`，保留原有 `limit` 1–10 截断行为，并保持数字字符串兼容（站点年份下拉框提交的是字符串）。

### `papertrail/server.py`

- 新增 `read_json_body`：要求 `Content-Length`，拒绝非整数、非正数和超过 `MAX_BODY_BYTES`（64 KiB）的请求体；拒绝非 UTF-8、非法 JSON 和非对象 JSON。
- 使用 `RequestError` 区分边界错误，分别返回 411、400、413；业务 `ValueError` 返回 400，未预期异常才返回 500。
- 处理顺序调整为“先解析请求体，再调用服务”，避免解析失败被误记为内部错误。

### 测试

- `tests/test_service.py`：覆盖非法 JSON、根节点类型、`papers` 类型、论文项类型、缺字段、`year`/`tags` 类型、重复 `id`、“全部校验后再写入”、非法搜索参数、数字字符串与 `null` 默认值、`limit` 截断。
- `tests/test_server.py`（新增）：启动本地 `ThreadingHTTPServer`，通过真实 HTTP 请求验证 200、400（空体、坏 JSON、数组、非 UTF-8、坏 `Content-Length`）、411、413、400（业务错误）、500（未预期错误）和 404。

## 测试结果

```bash
cd qoder
python -m pytest -q tests
```

```text
...............................                                          [100%]
31 passed in 5.93s
```

```bash
cd qoder
python scripts/verify.py
```

```text
{"imported": 6, "result_count": 1, "status": "passed"}
```

`verify.py` 同时重写了 `records/validation-preflight.json`，内容为 6 篇导入、查询 `long context retrieval quality`、年份下限 2020 及 1 条记录结果。

## pyseekdb 安装结果

已在 `qoder/.venv` 安装并验证 `pyseekdb 1.4.0.post1`：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt "pyseekdb==1.4.0.post1"
.venv/Scripts/python -m pip install "onnxruntime==1.19.2"
```

- `import pyseekdb` 正常，`pip check` 显示 `No broken requirements found`。
- `onnxruntime 1.31.1` 和 `1.22.1` 在该 Windows 主机加载 native DLL 时崩溃（访问冲突/DLL 初始化失败），固定为 `onnxruntime 1.19.2` 后正常。PaperTrail 自行生成向量，不使用 onnxruntime 推理。
- 嵌入式客户端按预期不可用：`pylibseekdb` 仅支持 Linux/macOS，Windows 必须连接 seekdb Server。
- server 模式已执行到 TCP 连接阶段；本机 `127.0.0.1:2881` 没有 seekdb Server，报 `WinError 10061`（目标计算机积极拒绝）。本机没有 Docker 或 WSL，未启动真实数据库。
- `requirements.txt` 的 pyseekdb 平台标记仍跳过 Windows；在 Windows 复现时需显式安装 pyseekdb，并固定可用的 onnxruntime 版本。

## 未执行项与限制

- 真实 seekdb 检索仍未执行；`verify.py` 使用记录型替身验证请求形状。真实检索需要在 Linux/macOS 使用嵌入式模式，或配置 `SEEKDB_HOST` 连接可用的 seekdb Server。
- 按要求未提交 git、未发布 Qoder Sites。
- 本环境无法生成 Qoder 账号 UID 和对话截图，记录中没有虚构这些证据。
