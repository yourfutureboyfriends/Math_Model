/**
 * actorHeaders — kept for call-site compatibility. Identity now comes from the signed JWT
 * that AuthContext attaches to every API request; the backend ignores X-User.
 */
export function currentActor(): string {
  try {
    return localStorage.getItem('macro_user') || 'system';
  } catch {
    return 'system';
  }
}

export function actorHeaders(extra?: Record<string, string>): Record<string, string> {
  return { 'X-User': currentActor(), ...(extra || {}) };
}
