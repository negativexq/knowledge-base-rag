import { beforeEach } from "vitest"
import "@testing-library/jest-dom/vitest"

const localStorageData = new Map<string, string>()
const localStorageStub: Storage = {
  getItem: (key) => localStorageData.get(key) ?? null,
  setItem: (key, value) => localStorageData.set(key, value),
  removeItem: (key) => localStorageData.delete(key),
  clear: () => localStorageData.clear(),
  key: (index) => Array.from(localStorageData.keys())[index] ?? null,
  get length() {
    return localStorageData.size
  },
}
Object.defineProperty(globalThis, "localStorage", { configurable: true, value: localStorageStub })

Object.defineProperty(window, "requestAnimationFrame", {
  writable: true,
  value: (callback: FrameRequestCallback) => {
    callback(0)
    return 0
  },
})

HTMLElement.prototype.scrollIntoView = () => undefined

// Pages may keep state in sessionStorage (the Playground conversation);
// every test starts from an empty one.
beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState(null, "", "/")
})

// Radix popovers measure their anchor; jsdom has no ResizeObserver.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.defineProperty(globalThis, "ResizeObserver", { configurable: true, value: ResizeObserverStub })
