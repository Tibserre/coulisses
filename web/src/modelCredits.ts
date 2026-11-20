import type { CatalogModel } from "./api.ts";

/** The credits the models' licences require (CC BY 4.0, ADR 0081 of the engine), as the
 *  engine's catalog writes them: one per model that has one, each once. */
export function modelCredits(catalog: CatalogModel[]): string[] {
  return [
    ...new Set(
      catalog
        .map((m) => m.attribution?.trim())
        .filter((text): text is string => Boolean(text)),
    ),
  ];
}
