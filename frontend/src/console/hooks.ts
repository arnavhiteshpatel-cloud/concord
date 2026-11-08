// Small hooks shared by the Milestone 3 lab panels: an action runner that keeps the
// server's refusal message inline, and a cancellable interval poller.

import { useCallback, useEffect, useRef, useState } from "react";
import { ConcordApiError } from "../sdk";

export function errorText(e: unknown): string {
  if (e instanceof ConcordApiError) return `${e.code}: ${e.message}`;
  return e instanceof Error ? e.message : String(e);
}

export interface Action {
  busy: boolean;
  error: string | null;
  /** Runs `fn`; on failure keeps the server's message in `error` and resolves to undefined. */
  run: <T>(fn: () => Promise<T>) => Promise<T | undefined>;
  clear: () => void;
}

/** `onError` also receives every refusal (the console writes them to the session log). */
export function useAction(onError?: (text: string) => void): Action {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      const text = errorText(e);
      setError(text);
      onErrorRef.current?.(text);
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  const clear = useCallback(() => setError(null), []);
  return { busy, error, run, clear };
}

/**
 * Polls `fetcher` every `intervalMs` while `key` is non-null; a new key starts afresh.
 * A failed poll clears the value (stale numbers are never shown as current) and stores
 * the error text.
 */
export function usePoll<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  intervalMs: number,
): { value: T | null; error: string | null; refresh: () => void } {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const gen = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const poll = useCallback(() => {
    const g = gen.current;
    fetcherRef.current()
      .then((v) => {
        if (g !== gen.current) return;
        setValue(v);
        setError(null);
      })
      .catch((e: unknown) => {
        if (g !== gen.current) return;
        setValue(null);
        setError(errorText(e));
      });
  }, []);

  useEffect(() => {
    gen.current += 1;
    setValue(null);
    setError(null);
    if (key === null) return;
    poll();
    const t = setInterval(poll, intervalMs);
    return () => {
      gen.current += 1;
      clearInterval(t);
    };
  }, [key, intervalMs, poll]);

  return { value, error, refresh: poll };
}
