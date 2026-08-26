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
