import "fake-indexeddb/auto";
import { webcrypto } from "node:crypto";

// jsdom 환경에 Web Crypto subtle 보장(저장 암복호화 테스트용).
if (!globalThis.crypto?.subtle) {
  Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
}
