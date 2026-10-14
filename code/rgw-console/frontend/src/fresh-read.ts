/** Retry only a busy fresh reader; each attempt still requests a new source read. */
export async function retryFreshRead<T>(
  read: () => Promise<T>,
  signal: AbortSignal,
  onWaiting: (attempt: number) => void,
  delays: readonly number[] = [1000, 2000],
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    signal.throwIfAborted();
    try { return await read(); }
    catch (error) {
      signal.throwIfAborted();
      const busy = error && typeof error === "object" && "code" in error && error.code === "COLLECTION_BUSY";
      if (!busy || attempt >= delays.length) throw error;
      onWaiting(attempt + 1);
      await waitForRetry(delays[attempt], signal);
    }
  }
}

function waitForRetry(delay: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, delay);
    signal.addEventListener("abort", abort, { once: true });
  });
}
