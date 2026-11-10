export type Backend = "webgpu" | "wasm";

export interface Chunk {
  id: string;
  text: string;
  embedding: number[];
  metadata: Record<string, string | number | boolean>;
}

export interface SearchHit {
  id: string;
  document: string;
  metadata: Record<string, unknown>;
  distance?: number;
  score?: number;
}

export interface Metrics {
  modelLoadMs?: number;
  embeddingMs?: number;
  writeMs?: number;
  queryEmbeddingMs?: number;
  seekdbMs?: number;
  endToEndMs?: number;
}
