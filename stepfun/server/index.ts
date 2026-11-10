import cors from "cors";
import express from "express";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import {
  FulltextIndexConfig,
  Schema,
  SeekdbClient,
  VectorIndexConfig,
} from "seekdb";
import { z } from "zod";

const PORT = Number(process.env.PORT ?? 8787);
const DB_PATH = resolve(process.env.SEEKDB_PATH ?? ".seekdb");
const DATABASE = process.env.SEEKDB_DATABASE ?? "stepfun_kb";
const DIMENSION = 384;

const client = new SeekdbClient({ path: DB_PATH, database: DATABASE });
const app = express();
app.use(cors({ origin: [/^http:\/\/localhost:\d+$/, /^http:\/\/127\.0\.0\.1:\d+$/] }));
app.use(express.json({ limit: "32mb" }));

const collectionName = (kb: string) => `kb_${kb.replace(/[^a-zA-Z0-9_]/g, "_").slice(0, 48)}`;

async function getCollection(kb: string) {
  return client.getCollection({ name: collectionName(kb) });
}

async function ensureCollection(kb: string) {
  try {
    return await getCollection(kb);
  } catch {
    return client.createCollection({
      name: collectionName(kb),
      schema: new Schema({
        fulltextIndex: new FulltextIndexConfig("ik", { ik_mode: "smart" }),
        vectorIndex: new VectorIndexConfig({
          hnsw: { dimension: DIMENSION, distance: "cosine" },
          embeddingFunction: null,
        }),
      }),
    });
  }
}

const vector = z.array(z.number().finite()).length(DIMENSION);
const importBody = z.object({
  knowledgeBase: z.string().min(1).max(48),
  chunks: z.array(z.object({
    id: z.string().min(1).max(160),
    text: z.string().min(1).max(100_000),
    embedding: vector,
    metadata: z.record(z.string(), z.union([z.string(), z.number(), z.boolean()])),
  })).min(1).max(512),
});

const searchBody = z.object({
  knowledgeBase: z.string().min(1).max(48),
  query: z.string().min(1).max(2_000),
  embedding: vector,
  limit: z.number().int().min(1).max(20).default(8),
});

app.get("/api/health", async (_request, response) => {
  response.json({ ok: true, database: DATABASE, path: DB_PATH, engine: "seekdb embedded" });
});

app.post("/api/import", async (request, response, next) => {
  try {
    const body = importBody.parse(request.body);
    const collection = await ensureCollection(body.knowledgeBase);
    const started = performance.now();
    await collection.upsert({
      ids: body.chunks.map((chunk) => chunk.id),
      documents: body.chunks.map((chunk) => chunk.text),
      embeddings: body.chunks.map((chunk) => chunk.embedding),
      metadatas: body.chunks.map((chunk) => chunk.metadata),
    });
    // seekdb add/upsert resolves only after the write and its indexes are visible.
    response.json({
      ok: true,
      count: body.chunks.length,
      collection: collectionName(body.knowledgeBase),
      writeAndRefreshMs: performance.now() - started,
    });
  } catch (error) { next(error); }
});

app.post("/api/search", async (request, response, next) => {
  try {
    const body = searchBody.parse(request.body);
    const collection = await getCollection(body.knowledgeBase);
    const started = performance.now();
    // One native seekdb operation performs full-text + ANN fusion and ranking.
    // No client-side merge or secondary in-memory retrieval is used.
    const result = await collection.hybridSearch({
      query: { whereDocument: { $contains: body.query } },
      knn: { queryEmbeddings: [body.embedding] },
      nResults: body.limit,
    });
    const elapsed = performance.now() - started;
    response.json({ ok: true, result, seekdbMs: elapsed });
  } catch (error) { next(error); }
});

app.delete("/api/knowledge-bases/:id", async (request, response, next) => {
  try {
    await client.deleteCollection(collectionName(request.params.id));
    response.status(204).end();
  } catch (error) { next(error); }
});

app.use((error: unknown, _request: express.Request, response: express.Response, _next: express.NextFunction) => {
  const message = error instanceof Error ? error.message : "Unknown error";
  response.status(error instanceof z.ZodError ? 400 : 500).json({ ok: false, error: message });
});

const dist = resolve("dist");
if (existsSync(dist)) {
  app.use(express.static(dist));
  app.get("/*path", (_request, response) => response.sendFile(resolve(dist, "index.html")));
}

const server = app.listen(PORT, "127.0.0.1", () => {
  console.log(`Stepfun knowledge base: http://127.0.0.1:${PORT}`);
  console.log(`seekdb embedded data: ${DB_PATH}`);
});

const close = async () => {
  server.close();
  await client.close();
};
process.once("SIGINT", close);
process.once("SIGTERM", close);
