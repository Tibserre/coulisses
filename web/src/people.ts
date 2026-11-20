import type { Person } from "./api.ts";

/** A name as compared: no accents, no case, no outer spaces. */
export const bare = (s: string) =>
  s.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase("fr").trim();

/** « Paul » taken: « Paul 2 », else « Paul 3 »… no two people bear exactly the same name. */
export function freeName(name: string, known: Pick<Person, "name">[]): string {
  const base = name.replace(/\s+\d+$/, ""); // « Paul 2 » taken: « Paul 3 », not « Paul 2 2 »
  for (let n = 2; ; n++) {
    const next = `${base} ${n}`;
    if (!known.some((p) => bare(p.name) === bare(next))) return next;
  }
}
