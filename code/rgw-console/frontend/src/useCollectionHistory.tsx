import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { CollectionPage, CollectionSummary } from "./as-is-contracts";
import { createRequestScope } from "./request-scope";

/** Server keyset pages; a filter change always starts a new cursor chain. */
export function useCollectionHistory(query: string, revision = 0) {
  const [items, setItems] = useState<CollectionSummary[]>([]);
  const [page, setPage] = useState(1);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requests = useRef(createRequestScope());
  const cursors = useRef<(string | undefined)[]>([undefined]);

  const load = async (index: number, reset = false) => {
    if (!query || index < 0 || (index > 0 && !cursors.current[index])) return;
    const sequence = requests.current.begin(true)!;
    if (reset) { cursors.current = [undefined]; setItems([]); setNextCursor(null); }
    const params = new URLSearchParams(query);
    params.delete("cursor");
    const cursor = cursors.current[index];
    if (cursor) params.set("cursor", cursor);
    // Keep the last successful page/cursor on a transient paging failure so it can be retried.
    setLoading(true); setError("");
    try {
      const value = await api<CollectionPage>(`/v1/as-is/collections?${params}`, { cache: "no-store" });
      if (!requests.current.current(sequence)) return;
      setItems(value.items); setPage(index + 1); setNextCursor(value.next_cursor);
      if (value.next_cursor) cursors.current[index + 1] = value.next_cursor;
      else cursors.current.length = index + 1;
    } catch (caught) {
      if (requests.current.current(sequence)) setError((caught as Error).message);
    } finally { if (requests.current.finish(sequence)) setLoading(false); }
  };
  useEffect(() => {
    if (query) { setPage(1); void load(0, true); }
    else { setPage(1); setItems([]); setLoading(false); setError(""); setNextCursor(null); }
    return () => { requests.current.invalidate(); };
  }, [query, revision]);

  return { items, page, hasMore: Boolean(nextCursor), loading, error,
    reload: () => load(0, true), previous: () => load(page - 2), next: () => load(page) };
}

export function useDebouncedValue(value: string, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => { const timer = window.setTimeout(() => setDebounced(value), delay); return () => window.clearTimeout(timer); }, [value, delay]);
  return debounced;
}

export function CollectionHistoryPager({ page, count, hasMore, busy, previous, next, retry }: {
  page: number; count: number; hasMore: boolean; busy: boolean; previous: () => void; next: () => void; retry?: () => void;
}) {
  return <div className="toolbar"><button className="button ghost" disabled={busy || page === 1} onClick={previous}>Trang mới hơn</button><span role="status">Trang {page} · {count} bộ As-is{busy ? " · Đang xử lý…" : hasMore ? " · Còn dữ liệu cũ hơn" : " · Đã tới cuối lịch sử phù hợp"}</span><button className="button ghost" disabled={busy || !hasMore} onClick={next}>Trang cũ hơn</button>{retry && <button className="button ghost" disabled={busy} onClick={retry}>Thử đọc lại lịch sử</button>}</div>;
}
