import path from "node:path"
import { fileURLToPath } from "node:url"
import type { ViteUserConfig } from "vitest/config"

const rootDir = path.dirname(fileURLToPath(import.meta.url))

const config: ViteUserConfig = {
  esbuild: {
    target: "es2020"
  },
  optimizeDeps: {
    exclude: ["bun:sqlite"]
  },
  ssr: {
    // Vitest must bundle @effect/vitest; a separate vitest copy breaks suite registration.
    noExternal: ["@effect/vitest"]
  },
  resolve: {
    // One physical `effect` install — duplicate copies break Context.Service identity in tests.
    dedupe: ["effect", "@effect/platform-bun", "@effect/platform-node", "@effect/sql-sqlite-bun", "@effect/vitest"],
    alias: {
      "@": path.resolve(rootDir, "apps/api/src"),
      vitest: path.resolve(rootDir, "node_modules/vitest")
    }
  }
}

export default config
