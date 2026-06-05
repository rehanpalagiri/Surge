const TOKEN_KEY = "surge_token";
const LEGACY_KEY = "viraliq_token"; // old key — auto-migrate so existing sessions survive
const AUTH_EVENT = "surge-auth";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  // One-time migration: move token from old key to new key
  const legacy = localStorage.getItem(LEGACY_KEY);
  if (legacy) {
    localStorage.setItem(TOKEN_KEY, legacy);
    localStorage.removeItem(LEGACY_KEY);
  }
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function isLoggedIn(): boolean {
  return !!getToken();
}
