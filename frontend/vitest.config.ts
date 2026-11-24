import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL(".", import.meta.url)) } },
  // tsconfig 의 jsx 는 Next 용 "preserve" 라 esbuild 가 고전 변환(React.createElement)으로 떨어진다.
  // Next 와 같은 자동 런타임으로 맞춰 .tsx 컴포넌트를 테스트에서 그대로 렌더할 수 있게 한다.
  esbuild: { jsx: "automatic" },
  test: { environment: "jsdom", setupFiles: ["./tests/setup.ts"], include: ["tests/**/*.test.ts"] },
});
