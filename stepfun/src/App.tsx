import { useMemo, useState } from "react";
import { hybridSearch, importChunks } from "./api";
import { splitText } from "./chunking";
import { embed, loadModel, MODEL_DTYPE, MODEL_ID } from "./embedding";
import type { Backend, Metrics, SearchHit } from "./types";

const BATCH_SIZE = 16;

const elapsed = (started: number) => performance.now() - started;
const formatMs = (value?: number) => value == null ? "—" : `${value.toFixed(1)} ms`;

export default function App() {
  const [backend, setBackend] = useState<Backend>();
  const [modelProgress, setModelProgress] = useState(0);
  const [knowledgeBase, setKnowledgeBase] = useState("personal");
  const [files, setFiles] = useState<File[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("等待导入文档");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [metrics, setMetrics] = useState<Metrics>({});
  const [documentCount, setDocumentCount] = useState(0);

  const backendLabel = useMemo(() => backend === "webgpu" ? "WebGPU · GPU 加速" : backend === "wasm" ? "WASM · CPU 降级" : "尚未加载", [backend]);

  async function ensureModel() {
    if (backend) return backend;
    setStatus("正在下载并加载 INT8 模型…");
    const started = performance.now();
    const selected = await loadModel(setModelProgress);
    setBackend(selected);
    setMetrics((previous) => ({ ...previous, modelLoadMs: elapsed(started) }));
    return selected;
  }

  async function handleImport() {
    if (!files.length) return;
    setBusy(true); setProgress(0); setHits([]);
    try {
      await ensureModel();
      const allChunks: Array<{ id: string; text: string; filename: string; chunk: number }> = [];
      for (const file of files) {
        const text = await file.text();
        splitText(text).forEach((part, index) => allChunks.push({
          id: `${file.name}-${file.lastModified}-${index}`,
          text: part, filename: file.name, chunk: index,
        }));
      }
      if (!allChunks.length) throw new Error("文档没有可导入的文本");
      setStatus(`正在浏览器本地向量化 0/${allChunks.length}…`);
      const embeddingStarted = performance.now();
      let imported = 0;
      let writeMs = 0;
      for (let offset = 0; offset < allChunks.length; offset += BATCH_SIZE) {
        const batch = allChunks.slice(offset, offset + BATCH_SIZE);
        const vectors = await embed(batch.map((chunk) => chunk.text));
        setStatus(`正在写入 seekdb ${Math.min(offset + batch.length, allChunks.length)}/${allChunks.length}…`);
        const result = await importChunks(knowledgeBase, batch.map((chunk, index) => ({
          id: chunk.id,
          text: chunk.text,
          embedding: vectors[index],
          metadata: { filename: chunk.filename, chunk: chunk.chunk, importedAt: new Date().toISOString() },
        })));
        writeMs += result.writeAndRefreshMs;
        imported += batch.length;
        setProgress(Math.round(imported / allChunks.length * 100));
      }
      setMetrics((previous) => ({ ...previous, embeddingMs: elapsed(embeddingStarted) - writeMs, writeMs }));
      setDocumentCount((count) => count + files.length);
      setStatus(`完成：${allChunks.length} 个片段已写入并可检索`);
    } catch (error) {
      setStatus(`失败：${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  }

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setBusy(true); setStatus("正在本地生成查询向量…");
    try {
      await ensureModel();
      const totalStarted = performance.now();
      const embeddingStarted = performance.now();
      const [queryVector] = await embed([query.trim()]);
      const queryEmbeddingMs = elapsed(embeddingStarted);
      setStatus("seekdb 正在执行原生混合检索…");
      const result = await hybridSearch(knowledgeBase, query.trim(), queryVector);
      setHits(result.hits);
      setMetrics((previous) => ({ ...previous, queryEmbeddingMs, seekdbMs: result.seekdbMs, endToEndMs: elapsed(totalStarted) }));
      setStatus(`找到 ${result.hits.length} 条结果`);
    } catch (error) {
      setStatus(`失败：${error instanceof Error ? error.message : String(error)}`);
    } finally { setBusy(false); }
  }

  return <main>
    <header>
      <div className="brand"><span className="mark">潮</span><div><strong>潮汐知识库</strong><small>ON-DEVICE AI × seekdb</small></div></div>
      <div className={`backend ${backend ?? "idle"}`}><i />{backendLabel}</div>
    </header>

    <section className="hero">
      <p className="eyebrow">PRIVATE BY DESIGN</p>
      <h1>让知识留在<br /><em>你的设备里</em></h1>
      <p>浏览器本地完成向量化，seekdb 原生融合语义与全文检索。没有云端推理，没有数据外传。</p>
      <div className="stats"><span><b>{documentCount}</b> 文档</span><span><b>{MODEL_DTYPE.toUpperCase()}</b> 量化</span><span><b>384</b> 维向量</span></div>
    </section>

    <div className="workspace">
      <section className="panel import-panel">
        <div className="panel-title"><span>01</span><div><h2>导入语料</h2><p>TXT / MD，支持连续增量写入</p></div></div>
        <label className="kb-label">知识库标识<input value={knowledgeBase} disabled={busy} onChange={(event) => setKnowledgeBase(event.target.value.replace(/[^a-zA-Z0-9_-]/g, ""))} /></label>
        <label className="dropzone">
          <input type="file" multiple accept=".txt,.md,text/plain,text/markdown" onChange={(event) => setFiles(Array.from(event.target.files ?? []))} />
          <span className="drop-icon">＋</span><b>选择或拖入文本文件</b><small>{files.length ? files.map((file) => file.name).join("、") : "文件只在浏览器内读取和编码"}</small>
        </label>
        <button className="primary" disabled={busy || !files.length || !knowledgeBase} onClick={handleImport}>本地向量化并写入</button>
        {(busy || progress > 0) && <div className="progress"><span style={{ width: `${progress || modelProgress}%` }} /></div>}
      </section>

      <section className="panel search-panel">
        <div className="panel-title"><span>02</span><div><h2>混合检索</h2><p>向量召回 + 全文检索，由 seekdb 融合排序</p></div></div>
        <form onSubmit={handleSearch}><input aria-label="查询" placeholder="输入你想查找的问题…" value={query} onChange={(event) => setQuery(event.target.value)} /><button disabled={busy || !query.trim()}>检索</button></form>
        <div className="status"><i />{status}</div>
        <div className="results">
          {hits.length === 0 ? <div className="empty"><span>≈</span><p>导入文档后，答案会从这里浮现</p></div> : hits.map((hit, index) => <article key={hit.id}>
            <div className="rank">{String(index + 1).padStart(2, "0")}</div>
            <div><div className="result-meta"><b>{String(hit.metadata.filename ?? "文档")}</b><span>{hit.score != null ? `融合分 ${hit.score.toFixed(3)}` : hit.distance != null ? `距离 ${hit.distance.toFixed(3)}` : "混合命中"}</span></div><p>{hit.document}</p></div>
          </article>)}
        </div>
      </section>
    </div>

    <section className="metrics">
      <h2>性能观测</h2><div>{Object.entries({ "模型加载": metrics.modelLoadMs, "文档向量化": metrics.embeddingMs, "写入与刷新": metrics.writeMs, "查询向量化": metrics.queryEmbeddingMs, "seekdb 检索": metrics.seekdbMs, "端到端": metrics.endToEndMs }).map(([label, value]) => <span key={label}><small>{label}</small><b>{formatMs(value)}</b></span>)}</div>
    </section>
    <footer><span>模型 {MODEL_ID} · INT8</span><span>所有 embedding 均在当前浏览器生成</span></footer>
  </main>;
}
