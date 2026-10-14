/** Prevent stale or unmounted requests from committing into a newer UI state. */
export function createRequestScope() {
  let generation = 0;
  let pending = false;
  return {
    begin(replace = false): number | undefined {
      if (pending && !replace) return undefined;
      pending = true;
      return ++generation;
    },
    current(token: number): boolean { return pending && token === generation; },
    finish(token: number): boolean {
      if (token !== generation) return false;
      pending = false;
      return true;
    },
    invalidate(): void { ++generation; pending = false; },
  };
}
