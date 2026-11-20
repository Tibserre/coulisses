/**
 * The version of the sound a session's page plays (`heard_version`, ADR 0074): the last one
 * known stays until another one comes; a null meanwhile (a conversion under way, the file
 * moved) changes nothing. A new version after a known one is a file replaced under an open
 * page: the player is reloaded where it was.
 */
export function nextHeardVersion(
  known: string | null,
  read: string | null,
): { version: string | null; reload: boolean } {
  if (read === null || read === known) return { version: known, reload: false };
  return { version: read, reload: known !== null };
}
