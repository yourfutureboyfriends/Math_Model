/** Bound both response headers and body reading, including unresponsive local proxies. */
export async function fetchJSONWithDeadline(url: string, parent: AbortSignal, timeoutMs = 60_000, init?: RequestInit) {
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancel: (() => void) | undefined;
  const stopped = new Promise<never>((_, reject) => {
    cancel = () => { reject(new DOMException('Request cancelled', 'AbortError')); controller.abort(); };
    if (parent.aborted) cancel();
    else parent.addEventListener('abort', cancel, { once: true });
    timer = setTimeout(() => {
      reject(new Error(`The data request timed out after ${timeoutMs / 1000} seconds. Retry when the feed is available.`));
      controller.abort();
    }, timeoutMs);
  });
  try {
    if (parent.aborted) return await stopped;
    return await Promise.race([
      (async () => {
        const response = await fetch(url, { ...init, signal: controller.signal });
        let invalid = false;
        const json = await response.json().catch(() => { invalid = true; return null; });
        return { response, json, invalid };
      })(), stopped,
    ]);
  } finally {
    clearTimeout(timer);
    if (cancel) parent.removeEventListener('abort', cancel);
  }
}
