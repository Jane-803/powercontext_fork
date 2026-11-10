import type { Chunk, SearchHit } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? `请求失败 (${response.status})`);
  return body as T;
}

export function importChunks(knowledgeBase: string, chunks: Chunk[]) {
  return request<{ count: number; writeAndRefreshMs: number }>("/api/import", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ knowledgeBase, chunks }),
  });
}

function firstRow<T>(value: T[] | T[][] | undefined): T[] {
  if (!value) return [];
  return Array.isArray(value[0]) ? (value[0] as T[]) : (value as T[]);
}

export async function hybridSearch(knowledgeBase: string, query: string, embedding: number[], limit = 8) {
  const response = await request<{ result: Record<string, unknown>; seekdbMs: number }>("/api/search", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ knowledgeBase, query, embedding, limit }),
  });
  const result = response.result as {
    ids?: string[] | string[][]; documents?: string[] | string[][];
    metadatas?: Record<string, unknown>[] | Record<string, unknown>[][];
    distances?: number[] | number[][]; scores?: number[] | number[][];
  };
  const ids = firstRow<string>(result.ids);
  const documents = firstRow<string>(result.documents);
  const metadatas = firstRow<Record<string, unknown>>(result.metadatas);
  const distances = firstRow<number>(result.distances);
  const scores = firstRow<number>(result.scores);
  const hits: SearchHit[] = ids.map((id, index) => ({
    id, document: documents[index] ?? "", metadata: metadatas[index] ?? ({} as Record<string, unknown>),
    distance: distances[index], score: scores[index],
  }));
  return { hits, seekdbMs: response.seekdbMs };
}
