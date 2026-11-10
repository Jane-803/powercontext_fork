import { env, pipeline, type FeatureExtractionPipeline } from "@huggingface/transformers";
import type { Backend } from "./types";

export const MODEL_ID = "Xenova/all-MiniLM-L6-v2";
export const MODEL_DTYPE = "q8";
export const EMBEDDING_DIMENSION = 384;

env.allowLocalModels = true;
env.useBrowserCache = true;

let extractor: FeatureExtractionPipeline | undefined;
let activeBackend: Backend | undefined;

async function loadFor(device: Backend, progress: (value: number) => void) {
  return pipeline("feature-extraction", MODEL_ID, {
    dtype: MODEL_DTYPE,
    device,
    progress_callback: (event) => {
      if ("progress" in event && typeof event.progress === "number") progress(Math.round(event.progress));
    },
  });
}

export async function loadModel(progress: (value: number) => void): Promise<Backend> {
  if (extractor && activeBackend) return activeBackend;
  if ("gpu" in navigator) {
    try {
      extractor = await loadFor("webgpu", progress);
      activeBackend = "webgpu";
      return activeBackend;
    } catch (error) {
      console.warn("WebGPU initialization failed; falling back to WASM", error);
    }
  }
  extractor = await loadFor("wasm", progress);
  activeBackend = "wasm";
  return activeBackend;
}

export async function embed(texts: string[]): Promise<number[][]> {
  if (!extractor) throw new Error("模型尚未加载");
  if (texts.length === 0) return [];
  const output = await extractor(texts, { pooling: "mean", normalize: true });
  return output.tolist() as number[][];
}
