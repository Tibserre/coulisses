/** A language model as the page says it (ADR 0051): « qwen3.8:27b-mlx » becomes « Qwen 3.8 –
 *  27b ». Read from Ollama's name only, never from a list in the code (P6): the family and its
 *  version, then the size the tag starts with. The exact name stays in developer mode. */

/** « qwen3.8 » → « Qwen 3.8 », « mistral-small3.2 » → « Mistral small 3.2 ». */
function family(base: string): string {
  const words = base
    .replace(/[-_]+/g, " ")
    .replace(/([a-z])(\d)/gi, "$1 $2")
    .trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The tag's parts: « 27b-mlx » → size « 27b », rest « mlx »; « latest » says nothing. */
function tagParts(tag: string): { size: string; rest: string } {
  if (tag === "" || tag === "latest") return { size: "", rest: "" };
  const [size, ...rest] = tag.split("-");
  return { size, rest: rest.join(" ") };
}

function split(name: string): { base: string; tag: string } {
  // « hf.co/user/model:tag », « user/model »: the model's own name is the last segment.
  const last = name.slice(name.lastIndexOf("/") + 1);
  const colon = last.indexOf(":");
  return colon < 0
    ? { base: last, tag: "" }
    : { base: last.slice(0, colon), tag: last.slice(colon + 1) };
}

function short(name: string): string {
  const { base, tag } = split(name);
  const { size } = tagParts(tag);
  return size ? `${family(base)} – ${size}` : family(base);
}

/** Each name's label among those listed together: two that would read the same keep the
 *  rest of their tag (« Qwen 3.5 – 9b nvfp4 »); two that still do keep their exact name, so
 *  no two choices look alike. */
export function ollamaLabels(names: readonly string[]): Map<string, string> {
  const unique = [...new Set(names)];
  const tally = (labels: Map<string, string>) => {
    const counts = new Map<string, number>();
    for (const label of labels.values()) counts.set(label, (counts.get(label) ?? 0) + 1);
    return counts;
  };
  const labels = new Map(unique.map((name) => [name, short(name)]));
  for (const pass of ["rest", "exact"] as const) {
    const counts = tally(labels);
    for (const name of unique) {
      const label = labels.get(name)!;
      if ((counts.get(label) ?? 0) < 2) continue;
      if (pass === "exact") labels.set(name, name);
      else {
        const { rest } = tagParts(split(name).tag);
        labels.set(name, rest ? `${short(name)} ${rest}` : name);
      }
    }
  }
  return labels;
}
