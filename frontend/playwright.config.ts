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
// The steering specs act on a run while it runs (ignore, focus, instruct, finish, pause); the
// outage spec needs a model that fails twice on the first node (NETGRIP_FAKE_SCENARIO=outage).
const steerDataDir = process.env.NETGRIP_E2E_STEER_DATA ?? mkdtempSync(join(tmpdir(), "netgrip-e2e-steer-"));
process.env.NETGRIP_E2E_STEER_DATA = steerDataDir;
const outageDataDir = process.env.NETGRIP_E2E_OUTAGE_DATA ?? mkdtempSync(join(tmpdir(), "netgrip-e2e-outage-"));
process.env.NETGRIP_E2E_OUTAGE_DATA = outageDataDir;
const steerPort = 8397;
const outagePort = 8396;

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  projects: [
    { name: "app", testIgnore: /(board|steering|report-steer|outage)\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${port}` } },
    { name: "board", testMatch: /board\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${boardPort}` } },
    { name: "steering", testMatch: /(steering|report-steer)\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${steerPort}` } },
    { name: "outage", testMatch: /outage\.spec\.ts/, use: { baseURL: `http://127.0.0.1:${outagePort}` } },
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
    {
      command: `cd ../backend && NETGRIP_FAKE=1 NETGRIP_FAKE_DELAY_MS=400 NETGRIP_PORT=${steerPort} NETGRIP_DATA_DIR=${steerDataDir} uv run netgrip`,
      url: `http://127.0.0.1:${steerPort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `cd ../backend && NETGRIP_FAKE=1 NETGRIP_FAKE_SCENARIO=outage NETGRIP_FAKE_DELAY_MS=100 NETGRIP_PORT=${outagePort} NETGRIP_DATA_DIR=${outageDataDir} uv run netgrip`,
      url: `http://127.0.0.1:${outagePort}/api/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
