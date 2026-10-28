/** The rows of the review building itself (ADR 0058): the text's lines in their order, what
 *  was marked during the recording slipped in at its time. A line whose time the engine did
 *  not measure keeps its place in the text: no time is made up for it, nothing is sorted
 *  on one (P2). */

export interface OutlineRow {
  key: string;
  at: number | null;
  kind: string;
  text: string;
}

export function outlineRows(
  lines: OutlineRow[],
  marks: OutlineRow[],
): OutlineRow[] {
  const pending = [...marks].sort((a, b) => (a.at ?? 0) - (b.at ?? 0));
  const rows: OutlineRow[] = [];
  for (const line of lines) {
    // Before a line of known time: what was marked earlier than it.
    if (line.at !== null)
      while (pending.length && (pending[0].at ?? 0) < line.at)
        rows.push(pending.shift()!);
    rows.push(line);
  }
  return [...rows, ...pending];
}
