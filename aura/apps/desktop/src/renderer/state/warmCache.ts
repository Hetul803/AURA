type CacheEntry<T> = {
  value: T;
  expiresAt: number;
};

const CACHE = new Map<string, CacheEntry<any>>();
const INFLIGHT = new Map<string, Promise<any>>();

export function readWarmValue<T>(key: string): T | null {
  const entry = CACHE.get(key);
  if (!entry) return null;
  if (entry.expiresAt <= Date.now()) {
    CACHE.delete(key);
    return null;
  }
  return entry.value as T;
}

export function writeWarmValue<T>(key: string, value: T, ttlMs: number): T {
  CACHE.set(key, { value, expiresAt: Date.now() + ttlMs });
  return value;
}

export function invalidateWarmValue(key: string) {
  CACHE.delete(key);
  INFLIGHT.delete(key);
}

export function invalidateWarmValues(keys: string[]) {
  for (const key of keys) invalidateWarmValue(key);
}

export async function getOrFetchWarm<T>(key: string, ttlMs: number, fetcher: () => Promise<T>, force = false): Promise<T> {
  if (!force) {
    const cached = readWarmValue<T>(key);
    if (cached !== null) return cached;
    const pending = INFLIGHT.get(key);
    if (pending) return pending as Promise<T>;
  }
  const request = fetcher().then((value) => writeWarmValue(key, value, ttlMs)).finally(() => {
    INFLIGHT.delete(key);
  });
  INFLIGHT.set(key, request);
  return request;
}
