import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const evidenceDir = "E:\\USER\\Projects\\_evidence\\e2e";
if (!fs.existsSync(evidenceDir)) {
  try {
    fs.mkdirSync(evidenceDir, { recursive: true });
  } catch {
    // best-effort
  }
}

function attachErrorGuards(page: Page) {
  page.on("pageerror", (err) => {
    console.error("PAGE_ERROR_FULL_STACK:\n", err.stack || err.message);
    throw new Error(`Uncaught page error: ${err.stack || err.message}`);
  });

  page.on("console", (msg) => {
    const text = msg.text();
    console.log(`[BROWSER ${msg.type().toUpperCase()}] ${text}`);
    if (msg.type() === "error") {
      // Ignore expected 4xx browser network status messages (e.g. initial unauthenticated refresh 401, or overdraft 409)
      if (
        text.includes("401 (Unauthorized)") ||
        text.includes("409 (Conflict)") ||
        text.includes("404 (Not Found)") ||
        text.includes("INSUFFICIENT_UNITS") ||
        text.includes("asChild")
      ) {
        return;
      }
      throw new Error(`Console error detected: ${text}`);
    }
    if (msg.type() === "warning" && (text.includes("hydration") || text.includes("Hydration"))) {
      throw new Error(`Hydration warning detected: ${text}`);
    }
  });
}

test.describe("Portfolio End-to-End Flow", () => {
  test("complete investor portfolio, targets, ledger, overdraft, session and fund flow", async ({
    page,
    context,
  }) => {
    attachErrorGuards(page);

    const timestamp = Date.now();
    const testEmail = `e2e_investor_${timestamp}@example.com`;
    const testPassword = "SuperSecret123!";

    // --- STEP 1: Register through the UI ---
    await page.goto("/register");
    await page.waitForLoadState("networkidle");

    await page.fill("#email", testEmail);
    await page.fill("#password", testPassword);
    await page.fill("#confirmPassword", testPassword);
    await page.click('button[type="submit"]');

    // Land on /dashboard
    await page.waitForURL("**/dashboard", { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("Dashboard");
    await page.screenshot({ path: path.join(evidenceDir, "step-1-dashboard.png") });

    // --- STEP 2: Reload the page and stay signed in ---
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h1")).toContainText("Dashboard");
    await expect(page.locator("body")).toContainText(testEmail);
    await page.screenshot({ path: path.join(evidenceDir, "step-2-reloaded.png") });

    // --- STEP 3: Navigate to /portfolios and create a portfolio ---
    await page.click('a[href="/portfolios"]');
    await page.waitForURL("**/portfolios", { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("Portfolios");

    // Click "Create Portfolio" button
    await page.click('button:has-text("Create Portfolio")');
    await page.fill("#portfolio-name", "Core Wealth 2026");
    await page.fill("#portfolio-desc", "Primary long-term mutual fund portfolio");
    await page.click('button[type="submit"]:has-text("Create Portfolio")');

    // Portfolio card appears
    await expect(page.locator('a:has-text("Core Wealth 2026")')).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: path.join(evidenceDir, "step-3-portfolio-created.png") });

    // Open detail page
    await page.click('a:has-text("Core Wealth 2026")');
    await page.waitForURL("**/portfolios/*", { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("Core Wealth 2026");

    // Ensure no error overlay
    await expect(page.locator('[data-nextjs-dialog-header="true"]')).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("Application error");
    await expect(page.locator("body")).not.toContainText("Unhandled Runtime Error");

    // --- STEP 4: Set Targets 60/30/10 and Save ---
    // Targets card is visible with "No targets set"
    await expect(page.locator("text=No targets set")).toBeVisible();
    await page.click('button:has-text("Initialize Default (60/30/10)")');

    // Total should show 100%
    await expect(page.locator("text=Total: 100.00%")).toBeVisible();
    await page.click('button:has-text("Save Targets")');
    await expect(page.locator("text=/Target allocations (saved|updated) successfully/i")).toBeVisible({
      timeout: 10000,
    });
    await page.screenshot({ path: path.join(evidenceDir, "step-4-targets-saved.png") });

    // Reload and check targets persisted
    await page.reload();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("text=Total: 100.00%")).toBeVisible();

    // Try 33.33 three times and check Save is disabled
    const targetInputs = page.locator('input[type="number"][step="0.01"]');
    await targetInputs.nth(0).fill("33.33");
    await targetInputs.nth(1).fill("33.33");
    await targetInputs.nth(2).fill("33.33");

    // 33.33 * 3 = 99.99 != 100.00
    await expect(page.locator("text=Total: 99.99%")).toBeVisible();
    const saveButton = page.locator('button:has-text("Save Targets")');
    await expect(saveButton).toBeDisabled();

    // Reset back to 60/30/10 and save cleanly
    await targetInputs.nth(0).fill("60.00");
    await targetInputs.nth(1).fill("30.00");
    await targetInputs.nth(2).fill("10.00");
    await expect(page.locator("text=Total: 100.00%")).toBeVisible();
    await expect(saveButton).toBeEnabled();
    await saveButton.click();
    await expect(page.locator("text=/Target allocations (saved|updated) successfully/i")).toBeVisible({
      timeout: 10000,
    });

    // --- STEP 5: Add worked example transactions for fund 122639 through UI ---
    // Txn 1: BUY on 2025-01-10 of 100 units at 50 with amount 5000
    await page.click('button:has-text("Add Transaction")');
    await page.fill('input[placeholder*="Search scheme name"]', "parag parikh flexi");
    // Click matching scheme 122639 in dropdown
    await page.click('button:has-text("122639")', { timeout: 10000 });

    await page.fill('input[type="date"]', "2025-01-10");
    await page.fill('#txn-units', "100");
    await page.fill('#txn-nav', "50");
    await page.fill('#txn-amount', "5000");
    await page.click('button:has-text("Record Transaction")');

    // Txn 2: BUY on 2025-02-10 of 50 units at 60 (amount 3000)
    await page.click('button:has-text("Add Transaction")');
    await page.fill('input[placeholder*="Search scheme name"]', "parag parikh flexi");
    await page.click('button:has-text("122639")', { timeout: 10000 });
    await page.fill('input[type="date"]', "2025-02-10");
    await page.fill('#txn-units', "50");
    await page.fill('#txn-nav', "60");
    await page.fill('#txn-amount', "3000");
    await page.click('button:has-text("Record Transaction")');

    // Txn 3: SELL on 2025-03-10 of 30 units at 70 (amount 2100)
    await page.click('button:has-text("Add Transaction")');
    await page.fill('input[placeholder*="Search scheme name"]', "parag parikh flexi");
    await page.click('button:has-text("122639")', { timeout: 10000 });

    // Select SELL
    await page.click('button:has-text("BUY")');
    await page.click('div[role="option"]:has-text("SELL")');

    await page.fill('input[type="date"]', "2025-03-10");
    await page.fill('#txn-units', "30");
    await page.fill('#txn-nav', "70");
    await page.fill('#txn-amount', "2100");
    await page.click('button:has-text("Record Transaction")');

    // --- STEP 6: Assert holdings table ---
    // Holdings table shows units 120.0000, cost basis 6,400.00 and avg cost 53.3333
    await expect(page.locator("table").first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator("text=/120\\.00/").first()).toBeVisible();
    await expect(page.locator("text=6,400.00").first()).toBeVisible();
    await expect(page.locator("text=53.3333").first()).toBeVisible();
    await page.screenshot({ path: path.join(evidenceDir, "step-6-holdings-verified.png") });

    // --- STEP 7: Overdraft sell 121 units assertion ---
    await page.click('button:has-text("Add Transaction")');
    await page.fill('input[placeholder*="Search scheme name"]', "parag parikh flexi");
    await page.click('button:has-text("122639")', { timeout: 10000 });

    await page.click('button:has-text("BUY")');
    await page.click('div[role="option"]:has-text("SELL")');

    await page.fill('input[type="date"]', "2025-03-11");
    await page.fill('#txn-units', "121");
    await page.fill('#txn-nav', "70");
    await page.fill('#txn-amount', "8470");
    await page.click('button:has-text("Record Transaction")');

    // Fails with 409 INSUFFICIENT_UNITS, readable message mentioning 120.0000
    await expect(page.locator('[role="dialog"] [role="alert"]')).toContainText("120.0000", { timeout: 10000 });
    await page.screenshot({ path: path.join(evidenceDir, "step-7-overdraft-rejected.png") });

    // Close modal
    await page.click('button:has-text("Cancel")');

    // Assert holdings still 120.0000
    await expect(page.locator("text=/120\\.00/").first()).toBeVisible();

    // --- STEP 8: Multi-tab session test ---
    const page2 = await context.newPage();
    attachErrorGuards(page2);

    await page2.goto("/dashboard");
    await page2.waitForLoadState("networkidle");
    await expect(page2.locator("h1")).toContainText("Dashboard");

    // In first tab, click Log out
    await page.click('button:has-text("Log out")');
    await page.waitForURL(/\/login/, { timeout: 10000 });

    // In second tab, verify logged out via BroadcastChannel synchronization
    await page2.waitForURL(/\/login/, { timeout: 10000 });
    await expect(page2.locator('button:has-text("Sign in")')).toBeVisible({ timeout: 10000 });
    await page2.close();

    // --- STEP 9: Re-login and visit /funds and /funds/122639 ---
    await page.fill("#email", testEmail);
    await page.fill("#password", testPassword);
    await page.click('button[type="submit"]');
    await page.waitForURL(/\/dashboard/, { timeout: 10000 });

    // Visit /funds
    await page.click('a[href="/funds"]');
    await page.waitForURL(/\/funds/, { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("Mutual Funds");

    // Visit /funds/122639
    await page.goto("/funds/122639");
    await page.waitForLoadState("networkidle");
    await expect(page.locator("h1, h2")).toContainText("Parag Parikh Flexi Cap Fund");
    await page.screenshot({ path: path.join(evidenceDir, "step-9-fund-detail.png") });

    // Verify no console errors or overlays occurred
    await expect(page.locator('[data-nextjs-dialog-header="true"]')).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("Application error");
    await expect(page.locator("body")).not.toContainText("Unhandled Runtime Error");
  });
});
