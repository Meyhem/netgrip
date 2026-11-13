import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

// The config is loaded again in each worker: the data dirs are made once and passed on.
const dataDir = process.env.NETGRIP_E2E_DATA ?? mkdtempSync(join(tmpdir(), "netgrip-e2e-"));
process.env.NETGRIP_E2E_DATA = dataDir;
const boardDataDir = process.env.NETGRIP_E2E_BOARD_DATA ?? mkdtempSync(join(tmpdir(), "netgrip-e2e-board-"));
process.env.NETGRIP_E2E_BOARD_DATA = boardDataDir;
const port = 8399;
// The board specs watch a run while it runs: a second fake server whose model calls are slowed
// (NETGRIP_FAKE_DELAY_MS), so a run lasts long enough to click, reload and drop the stream, and
// streamed model text stays on screen for a while. Web servers start in order: the first one
// builds the frontend that both serve.
const boardPort = 8398;
const boardDelayMs = 600;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  projects: [
    { name: "app", testIgnore: /board\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${port}` } },
    { name: "board", testMatch: /board\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${boardPort}` } },
  ],
  webServer: [
    {
      command: `npm run build && cd ../backend && NETGRIP_FAKE=1 NETGRIP_PORT=${port} NETGRIP_DATA_DIR=${dataDir} uv run netgrip`,
      url: `http://127.0.0.1:${port}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `cd ../backend && NETGRIP_FAKE=1 NETGRIP_FAKE_DELAY_MS=${boardDelayMs} NETGRIP_PORT=${boardPort} NETGRIP_DATA_DIR=${boardDataDir} uv run netgrip`,
      url: `http://127.0.0.1:${boardPort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
