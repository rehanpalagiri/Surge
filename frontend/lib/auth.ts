const TOKEN_KEY = "viraliq_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
  // Let other components (e.g. the nav) react to auth changes.
  window.dispatchEvent(new Event("viraliq-auth"));
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  window.dispatchEvent(new Event("viraliq-auth"));
}

export function isLoggedIn(): boolean {
  return !!getToken();
}
