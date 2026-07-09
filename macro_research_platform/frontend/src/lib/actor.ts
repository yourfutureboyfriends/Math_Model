/**
 * actorHeaders — attach the logged-in user to state-changing requests so the backend
 * audit trail records who actually acted (the demo token carries no identity).
 * The username is persisted to localStorage on login by AuthContext.
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
