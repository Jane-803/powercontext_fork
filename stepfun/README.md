# 潮汐知识库：浏览器端 Embedding × seekdb 混合检索

本项目完成比赛要求的完整链路：浏览器读取 TXT/Markdown → 浏览器内批量生成 embedding → 写入 seekdb → seekdb 原生混合检索 → 展示原文与分阶段耗时。代码不调用任何云端推理 API。

## 快速启动

要求 Node.js 20+，Chrome / Edge 最新版。

```bash
cd stepfun
pnpm install
pnpm dev
```

浏览器访问 `http://localhost:5173`。开发模式会同时启动 Vite 前端和 `127.0.0.1:8787` 的本地服务。seekdb 使用嵌入式模式，数据库默认存放在 `stepfun/.seekdb`。

生产方式：

```bash
pnpm build
pnpm start
```

随后访问 `http://127.0.0.1:8787`。首次使用会从 Hugging Face 下载公开模型；下载只提供模型文件，embedding 计算仍在浏览器设备本地发生。模型文件随后使用浏览器 Cache API 缓存。

## 验收操作

1. 打开页面，选择 `testdata/corpus/seekdb.txt`，点击“本地向量化并写入”。
2. 观察右上角显示 `WebGPU · GPU 加速`；禁用 WebGPU 后刷新，应显示 `WASM · CPU 降级`。
3. 查询“混合检索在哪里完成？”，确认返回原文，且性能区显示查询向量化、seekdb 检索和端到端耗时。
4. 再导入另一个文本文件，不刷新页面直接搜索新内容，验证增量写入和索引可见性。
5. 修改知识库标识可切换集合；结果不会跨集合泄漏。

## 架构与合规边界

```text
Browser: File API → chunk → Transformers.js(q8) → 384-d vectors
                                      │
                                      ▼ JSON (vector + text + metadata)
Local Node: seekdb-js → embedded seekdb collection
                     → collection.hybridSearch(fulltext + KNN)
```

- 文档和查询 embedding 都由 `@huggingface/transformers` 在浏览器执行。
- 后端显式优先 `device: "webgpu"`，初始化失败自动以 `device: "wasm"` 重试并在 UI 标明。
- 服务端没有 embedding 依赖，只接收浏览器生成的向量。
- 混合检索只有一次 `collection.hybridSearch()` 调用；前端不分别查询、不自行拼接或重排。
- 每个知识库映射为独立 seekdb collection；稳定 ID + `upsert` 支持幂等增量导入。
- `upsert` Promise 完成后才向前端返回成功，此时写入和索引更新已经可见。

## 命令

| 命令 | 用途 |
|---|---|
| `pnpm dev` | 前后端开发启动 |
| `pnpm build` | TypeScript 检查和生产构建 |
| `pnpm start` | 启动生产服务 |
| `pnpm test` | 单元测试 |
| `pnpm check` | TypeScript 静态检查 |

环境变量见 `.env.example`。测试语料、查询与指标函数分别位于 `testdata/` 和 `scripts/benchmark.mjs`。

## 模型许可与来源

- 模型：[Xenova/all-MiniLM-L6-v2](https://huggingface.co/Xenova/all-MiniLM-L6-v2)，对应 Sentence Transformers `all-MiniLM-L6-v2`，Apache-2.0。
- 运行时：`@huggingface/transformers` 4.3.2 / ONNX Runtime Web。
- 量化文件：仓库发布的 ONNX INT8（Transformers.js `dtype: "q8"`）。

完整设计、测量口径和记录表见 [TECHNICAL_NOTE.md](TECHNICAL_NOTE.md)。
