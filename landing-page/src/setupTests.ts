import "@testing-library/jest-dom/vitest";

// jsdom の localStorage を明示的にグローバルへ公開する
if (typeof globalThis.localStorage === "undefined") {
  const store = new Map<string, string>();
  globalThis.localStorage = {
    getItem: (key: string): string | null => store.get(key) ?? null,
    setItem: (key: string, value: string): void => {
      store.set(key, value);
    },
    removeItem: (key: string): void => {
      store.delete(key);
    },
    clear: (): void => {
      store.clear();
    },
    get length(): number {
      return store.size;
    },
    key: (index: number): string | null => Array.from(store.keys())[index] ?? null,
  };
}

class ResizeObserverMock {
  observe(): void {
    // mock implementation
  }

  unobserve(): void {
    // mock implementation
  }

  disconnect(): void {
    // mock implementation
  }
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverMock;
}

// jsdom の matchMedia は環境依存のため、全テストで決定的に動作するモックへ置き換える
globalThis.matchMedia = (query: string): MediaQueryList =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addListener: (): void => {
      /* noop */
    },
    removeListener: (): void => {
      /* noop */
    },
    addEventListener: (): void => {
      /* noop */
    },
    removeEventListener: (): void => {
      /* noop */
    },
    dispatchEvent: (): boolean => false,
  }) as MediaQueryList;
