# 一页技术说明：端侧 AI 推理与 seekdb 混合检索

## 模型与量化

使用公开模型 `Xenova/all-MiniLM-L6-v2`（384 维，Apache-2.0）及 Transformers.js 4.3.2。生产配置显式指定 `dtype: "q8"`，加载 Hugging Face 仓库内官方 ONNX INT8 权重。按模型仓库 2026-11-10 文件元数据的同口径统计：FP32 `model.onnx` 为 90,387,606 B（86.20 MiB），INT8 `model_quantized.onnx` 为 22,972,370 B（21.91 MiB），压缩比 **3.93×**，减少 74.58%。两者使用相同 tokenizer、mean pooling 与 L2 normalization。质量评估使用 `testdata/queries.json`，分别切换 `dtype: "fp32"` 与 `"q8"`，以 Recall@5、nDCG@5 报告；指标函数在 `scripts/benchmark.mjs`，避免主观挑选样例。

## 端侧运行与降级

文档和查询向量都在浏览器内生成，服务端只接收向量、原文和元数据，不存在云端推理接口。加载器先以 `device: "webgpu"` 初始化；浏览器无 `navigator.gpu` 或 WebGPU 初始化异常时，捕获错误并以 `device: "wasm"` 重建 pipeline。界面右上角持续显示实际后端。模型通过浏览器缓存复用；文档按 **16 条/批** 推理和写入，在峰值内存、GPU 利用率与首批可写入时间间折中。首次模型下载/加载与预热后的查询分开计时。

## seekdb 数据层

本地 Node 服务使用 `seekdb` 1.4.0 嵌入式模式。每个知识库为独立 collection，schema 同时创建 IK smart 全文索引与 384 维 cosine HNSW 索引；记录包含稳定片段 ID、原文、浏览器生成的 dense vector、文件名、片段序号与导入时间。导入采用 `upsert`，支持连续增量导入和重复文件幂等覆盖。服务仅在 `upsert` 完成后报告成功，保证索引可见。查询只调用一次 seekdb `collection.hybridSearch({query, knn})`，由数据库执行全文与向量融合排序；客户端没有两路召回或结果拼接。知识库标识随每次写入/查询传递，避免切换后的会话串库。

## 性能优化与复现记录

优化点包括 q8 权重、模型/浏览器缓存、批量推理、批量 upsert、一次原生混合检索、稳定集合复用。页面直接显示模型加载、文档向量化、写入与刷新、查询向量化、seekdb 检索及端到端延迟。固定同一设备、Chrome/Edge 版本、语料与查询；每种配置冷启动 1 次，预热后重复 10 次，保留原始值并报告中位数。提交者应在实际提测设备执行后填写下表；未运行的数字不伪造。

| 配置 | 模型体积 | 向量化吞吐 | seekdb 中位延迟 | 端到端中位延迟 | Recall@5 / nDCG@5 |
|---|---:|---:|---:|---:|---:|
| FP32 基线 | 86.20 MiB | 待实测 | 待实测 | 待实测 | 待实测 |
| INT8 + WebGPU | 21.91 MiB | 待实测 | 待实测 | 待实测 | 待实测 |
| INT8 + WASM | 21.91 MiB | 待实测 | 待实测 | 待实测 | 待实测 |

验收时应同时截图 WebGPU 与禁用 WebGPU 后的 WASM 标识，并保存浏览器控制台导出的原始样本。功能与计时复现步骤见 README。
