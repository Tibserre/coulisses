import { useEffect, useState } from "react";

/** Developer mode: technical details (versions, memory, provenance, raw errors) are
 *  hidden unless it is on. A per-browser convenience, never a source of truth. */
const KEY = "coulisses.mode-developpeur";
const EVENT = "coulisses:mode-developpeur";

function read(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false; // storage blocked: the default (off) is the safe choice
  }
}

export function setDevMode(on: boolean): void {
  try {
    window.localStorage.setItem(KEY, on ? "1" : "0");
  } catch {
    // Storage blocked: the switch still works for this page.
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: on }));
}

export function useDevMode(): boolean {
  const [on, setOn] = useState(read);
  useEffect(() => {
    const onChange = (e: Event) => setOn((e as CustomEvent<boolean>).detail);
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);
  return on;
}
