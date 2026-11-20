/**
 * What a key does on the recording screen (spec §7.2, ADR 0089). In a field or a dialog
 * (« Qui est là ? »), keys keep their own meaning; on a button reached by Tab, Space presses
 * it. Held (paused, or stopping): Space, or Escape while it stops, takes it back; nothing
 * else. Recording: Space pauses, J and D play or discussion, M a key moment, N annotates.
 */
export type KeyAction = "toggle" | "scene" | "discussion" | "moment" | "annotate" | null;

export function recordingKey(
  key: string,
  where: { inField: boolean; onButton: boolean },
  held: { held: boolean; stopping: boolean },
): KeyAction {
  if (where.inField) return null;
  if (key === " " && where.onButton && held.held) return null;
  if (held.held) return key === " " || (key === "escape" && held.stopping) ? "toggle" : null;
  if (key === " ") return "toggle";
  if (key === "j") return "scene";
  if (key === "d") return "discussion";
  if (key === "m") return "moment";
  if (key === "n") return "annotate";
  return null;
}
