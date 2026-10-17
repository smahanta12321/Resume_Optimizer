/**
 * The local API's per-launch session token. `python -m src.api` prints a link with
 * `#token=...`; the token is moved into sessionStorage and removed from the address bar.
 * sessionStorage (not localStorage): the token changes every launch and shouldn't outlive the tab.
 */
const KEY = "ro-session-token";

let memoryToken: string | null = null;

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? memoryToken;
  } catch {
    return memoryToken;
  }
}

export function setToken(token: string): void {
  memoryToken = token.trim();
  try {
    sessionStorage.setItem(KEY, memoryToken);
  } catch {
    // Storage blocked: keep it in memory for this page load.
  }
}

export function clearToken(): void {
  memoryToken = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

/** Reads `#token=...` from the URL once, stores it, and strips it from history. */
export function captureTokenFromUrl(): void {
  const match = /(?:^#|&)token=([^&]+)/.exec(window.location.hash);
  if (!match?.[1]) return;
  setToken(decodeURIComponent(match[1]));
  window.history.replaceState(window.history.state, "", window.location.pathname + window.location.search);
}
