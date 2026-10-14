import type { ModelsInfo } from "./api.ts";

/** What the Rédaction tab says to get writing going on this Mac (lot 11g of the plan):
 *  install Ollama, install the model advised for its memory, or pick one; and a warning
 *  under the memory writing needs. Nothing is downloaded by Coulisses (P1). */
export type AdviceStep =
  | { kind: "install-ollama" }
  | { kind: "pull"; model: string; command: string }
  | { kind: "ready"; model: string }
  | { kind: "choose" }
  | { kind: "none" };

export const OLLAMA_DOWNLOAD = "https://ollama.com/download";
export const OLLAMA_LIBRARY = "https://ollama.com/library";

export function adviceStep(info: ModelsInfo): AdviceStep {
  if (!info.reachable) return { kind: "install-ollama" };
  const model = info.advice?.model ?? null;
  if (model !== null) {
    return info.advice.installed
      ? { kind: "ready", model }
      : { kind: "pull", model, command: `ollama pull ${model}` };
  }
  return info.models.length === 0 ? { kind: "choose" } : { kind: "none" };
}

/** The Mac's memory when writing may run short of it, else null. */
export function shortMemory(info: ModelsInfo): number | null {
  const memory = info.advice?.memory_gb ?? null;
  return memory !== null && memory < info.advice.minimum_gb
    ? Math.round(memory)
    : null;
}

/** The Mac's memory could not be read: no model can be advised to it (said, not guessed). */
export function memoryUnknown(info: ModelsInfo): boolean {
  return info.advice !== undefined && info.advice.memory_gb === null;
}
