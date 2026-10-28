// The fund the app works on (several funds, each with its own book, settings and audit log — api/funds.py).
// Remembered per browser; sent on every API call as the X-Fund header by the fetch wrapper (context/AuthContext).
const KEY = 'macro.fund';

export function currentFund(): string {
  try { return localStorage.getItem(KEY) || 'main'; } catch { return 'main'; }
}

export function switchFund(id: string): void {
  try { localStorage.setItem(KEY, id); } catch { /* private window: stays on this page only */ }
  window.location.reload();                 // every panel re-reads the chosen fund's book
}
