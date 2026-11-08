import { defineConfig } from "@playwright/test";
import * as path from "path";

// Ensure PLAYWRIGHT_BROWSERS_PATH defaults to D:\caches\playwright
if (!process.env.PLAYWRIGHT_BROWSERS_PATH) {
  process.env.PLAYWRIGHT_BROWSERS_PATH = "D:\\caches\\playwright";
}

const evidenceDir = "E:\\USER\\Projects\\_evidence\\e2e";

export default defineConfig({
  testDir: "./e2e",
  timeout: 45 * 1000,
  expect: {
    timeout: 10 * 1000,
  },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  outputDir: path.join(evidenceDir, "test-results"),
  reporter: [
    ["list"],
    [
      "html",
      {
        outputFolder: path.join(evidenceDir, "report"),
        open: "never",
      },
    ],
  ],
  use: {
    baseURL: process.env.PLAYWRIGHT_TEST_BASE_URL || "http://localhost:3000",
    headless: true,
    screenshot: "on",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        browserName: "chromium",
      },
    },
  ],
});

