/** The text as the app shows it (SummaryView's SAFE_RENDERERS): an image keeps only its
 *  description, a link only its text, raw HTML shows as text. Copied, then pasted in an
 *  editor that loads remote images, a text written by the model can fetch nothing (P1;
 *  security review of 2026-10-13). Nothing else changes. Same as summaries.inert_markdown
 *  on the service, for the Markdown export. */
// Every form of image: inline, by reference, collapsed and shortcut (`![alt]`).
const IMAGE = /!\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])?/g;
const LINK = /(?<!!)\[([^\]]+)\]\([^)]*\)/g;
const TAG = /<(?=[A-Za-z/!?])/g;

export function inertMarkdown(text: string): string {
  return text.replace(IMAGE, "$1").replace(LINK, "$1").replace(TAG, "&lt;");
}
