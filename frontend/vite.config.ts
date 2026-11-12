/// <reference types="vitest" />
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const ds = fileURLToPath(new URL("../design-system/project", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@ds": ds } },
  server: {
    fs: { allow: [".", ds] },
    proxy: { "/api": "http://127.0.0.1:8321" },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
