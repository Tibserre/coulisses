/** The summaries of a session as tabs (ADR 0060): one per summary written or being written,
 *  in the order they were first asked, the space's own summary first. Each tab shows the
 *  latest version of its summary; the older ones stay on the disk (P5). */
import type { ActionInfo, Generation, PendingGeneration } from "./api.ts";

export interface SummaryTab {
  ref: string;
  name: string;
  /** Its latest version; none while the first one is being written. */
  latest: Generation | null;
  /** A version being written, waiting, or failed. */
  pending: PendingGeneration | null;
}

export function summaryTabs(
  generations: Generation[],
  pending: PendingGeneration[],
  preferred: string | null,
): SummaryTab[] {
  // `generations` comes latest first: the first one met is each summary's latest.
  const tabs = new Map<string, SummaryTab & { first: number }>();
  for (const g of generations) {
    const tab = tabs.get(g.action_ref);
    if (tab) tab.first = Math.min(tab.first, g.id);
    else
      tabs.set(g.action_ref, {
        ref: g.action_ref,
        name: g.action_name,
        latest: g,
        pending: null,
        first: g.id,
      });
  }
  for (const p of pending) {
    const tab = tabs.get(p.action_ref);
    if (tab) tab.pending = p;
    else
      tabs.set(p.action_ref, {
        ref: p.action_ref,
        name: p.action_name,
        latest: null,
        pending: p,
        first: Number.MAX_SAFE_INTEGER - pending.length + pending.indexOf(p),
      });
  }
  return [...tabs.values()]
    .sort(
      (a, b) =>
        Number(b.ref === preferred) - Number(a.ref === preferred) ||
        a.first - b.first,
    )
    .map(({ ref, name, latest, pending }) => ({ ref, name, latest, pending }));
}

/** The summaries not written yet, to offer under « + Rédiger… »: the space's own first. */
export function writable(
  actions: ActionInfo[],
  tabs: SummaryTab[],
  preferred: string | null,
): ActionInfo[] {
  const taken = new Set(tabs.map((t) => t.ref));
  return actions
    .filter((a) => !taken.has(a.ref))
    .sort((a, b) => Number(b.ref === preferred) - Number(a.ref === preferred));
}
