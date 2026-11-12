import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

const dataDir = process.env.NETGRIP_E2E_DATA ?? mkdtempSync(join(tmpdir(), "netgrip-e2e-"));
process.env.NETGRIP_E2E_DATA = dataDir;
const port = 8399;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  use: { baseURL: `http://127.0.0.1:${port}` },
  webServer: {
    command: `npm run build && cd ../backend && NETGRIP_FAKE=1 NETGRIP_PORT=${port} NETGRIP_DATA_DIR=${dataDir} uv run netgrip`,
    url: `http://127.0.0.1:${port}/api/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
