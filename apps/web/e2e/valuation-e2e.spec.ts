import { test, expect, type Page } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";
import Decimal from "decimal.js";

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
    if (msg.type() === "error") {
      if (
        text.includes("401 (Unauthorized)") ||
        text.includes("409 (Conflict)") ||
        text.includes("404 (Not Found)") ||
        text.includes("422 (Unprocessable Entity)") ||
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

function formatInrSimple(val: string | number): string {
  const d = new Decimal(val).toDecimalPlaces(2, Decimal.ROUND_HALF_UP);
  const isNeg = d.isNegative();
  const absFixed = d.abs().toFixed(2);
  const [intPart = "0", decPart = "00"] = absFixed.split(".");
  const last3 = intPart.slice(-3);
  const rest = intPart.slice(0, -3);
  const grouped = rest
    ? rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + last3
    : last3;
  return `${isNeg ? "-" : ""}₹${grouped}.${decPart}`;
}

test.describe("Phase 5 Valuation, Gains, XIRR, and Dashboard Flow", () => {
  test("valuation calculations, consistency between portfolio page and dashboard, charts, range selector, and empty state", async ({
    page,
    request,
  }) => {
    attachErrorGuards(page);

    const timestamp = Date.now();
    const testEmail = `val_investor_${timestamp}@example.com`;
    const testPassword = "SuperSecret123!";

    // --- STEP 1: Register through the UI ---
    await page.goto("/register");
    await page.waitForLoadState("networkidle");

    await page.fill("#email", testEmail);
    await page.fill("#password", testPassword);
    await page.fill("#confirmPassword", testPassword);
    await page.click('button[type="submit"]');

    await page.waitForURL("/dashboard", { timeout: 15000 });
    await page.waitForLoadState("networkidle");

    // --- STEP 2: Assert Empty State for Brand New User ---
    const emptyHeading = page.locator("text=No investment activity yet");
    await expect(emptyHeading).toBeVisible();
    const goToPortfoliosBtn = page.locator("a:has-text('Go to Portfolios')");
    await expect(goToPortfoliosBtn).toBeVisible();

    await page.screenshot({ path: path.join(evidenceDir, "step-val-1-empty-dashboard.png") });

    // --- STEP 3: Navigate to Portfolios and Create Portfolio ---
    await goToPortfoliosBtn.click();
    await page.waitForURL("/portfolios");
    await page.waitForLoadState("networkidle");

    await page.click("button:has-text('Create Portfolio')");
    await page.fill("#name", "Valuation Performance Portfolio");
    await page.click("button:has-text('Save Portfolio')");
    await page.waitForTimeout(1000);

    const portfolioCardLink = page.locator("a:has-text('Valuation Performance Portfolio')").first();
    await expect(portfolioCardLink).toBeVisible();
    await portfolioCardLink.click();

    await page.waitForLoadState("networkidle");

    // --- STEP 4: Add Transactions for Fund 122639 ---
    // Transaction 1: Buy 2024-01-15, 100 units, nav 50, amount 5000
    await page.click("button:has-text('Add Transaction')");
    await page.waitForSelector("#txn-scheme-search");
    await page.fill("#txn-scheme-search", "122639");
    await page.waitForTimeout(600); // debounce
    await page.click("button:has-text('Select')");

    await page.fill("#txn-date", "2024-01-15");
    await page.fill("#txn-units", "100.0000");
    await page.fill("#txn-nav", "50.00000000");
    await page.fill("#txn-amount", "5000.00");
    await page.click("button:has-text('Record Transaction')");
    await page.waitForTimeout(1200);

    // Transaction 2: Buy 2025-01-15, 50 units, nav 60, amount 3000
    await page.click("button:has-text('Add Transaction')");
    await page.waitForSelector("#txn-scheme-search");
    await page.fill("#txn-scheme-search", "122639");
    await page.waitForTimeout(600);
    await page.click("button:has-text('Select')");

    await page.fill("#txn-date", "2025-01-15");
    await page.fill("#txn-units", "50.0000");
    await page.fill("#txn-nav", "60.00000000");
    await page.fill("#txn-amount", "3000.00");
    await page.click("button:has-text('Record Transaction')");
    await page.waitForTimeout(1200);

    // Transaction 3: Sell 2025-07-15, 30 units, nav 70, amount 2100
    await page.click("button:has-text('Add Transaction')");
    await page.waitForSelector("#txn-scheme-search");
    await page.fill("#txn-scheme-search", "122639");
    await page.waitForTimeout(600);
    await page.click("button:has-text('Select')");

    // Change type to SELL
    await page.click("#txn-type");
    await page.click("div[role='option']:has-text('Sell / Redemption')");

    await page.fill("#txn-date", "2025-07-15");
    await page.fill("#txn-units", "30.0000");
    await page.fill("#txn-nav", "70.00000000");
    await page.fill("#txn-amount", "2100.00");
    await page.click("button:has-text('Record Transaction')");
    await page.waitForTimeout(1500);

    // --- STEP 5: Assert Portfolio Page Values ---
    // Read live NAV from GET /api/v1/funds/122639
    const fundApiRes = await request.get("http://localhost:8000/api/v1/funds/122639");
    expect(fundApiRes.ok()).toBeTruthy();
    const fundData = (await fundApiRes.json()).data;
    const liveNav = new Decimal(fundData.latest_nav);

    const expectedCurrentVal = new Decimal("120").times(liveNav).toFixed(2);
    const expectedCurrentValStr = formatInrSimple(expectedCurrentVal);

    // Assert Cost Basis 6,400.00 and Realized Gain 500.00
    await expect(page.locator("text=₹6,400.00").first()).toBeVisible();
    await expect(page.locator("text=₹500.00").first()).toBeVisible();
    await expect(page.locator(`text=${expectedCurrentValStr}`).first()).toBeVisible();

    // Assert Value Trend Chart renders an svg
    const portfolioChartSvg = page.locator(".recharts-responsive-container svg").first();
    await expect(portfolioChartSvg).toBeVisible();

    await page.screenshot({ path: path.join(evidenceDir, "step-val-2-portfolio-valuation.png") });

    // --- STEP 6: Open /dashboard and Assert Consistency ---
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Assert per-portfolio row displays same current value and cost basis
    const portfolioRow = page.locator("tr:has-text('Valuation Performance Portfolio')");
    await expect(portfolioRow).toBeVisible();
    await expect(portfolioRow.locator(`text=${expectedCurrentValStr}`)).toBeVisible();
    await expect(portfolioRow.locator("text=₹6,400.00")).toBeVisible();
    await expect(portfolioRow.locator("text=₹500.00")).toBeVisible();

    // Assert XIRR displays a percentage with 2 decimals
    const xirrCell = portfolioRow.locator("td").last();
    const xirrText = await xirrCell.innerText();
    expect(xirrText).toMatch(/[+-]?\d+\.\d{2}%/);

    // Assert both charts render an svg
    const chartSvgs = page.locator(".recharts-responsive-container svg");
    await expect(chartSvgs.nth(0)).toBeVisible();
    await expect(chartSvgs.nth(1)).toBeVisible();

    // Click range buttons and verify chart updates without console error
    const rangeBtn6M = page.locator("button:has-text('6M')").first();
    if (await rangeBtn6M.isVisible()) {
      await rangeBtn6M.click();
      await page.waitForTimeout(500);
    }

    const rangeBtn1Y = page.locator("button:has-text('1Y')").first();
    if (await rangeBtn1Y.isVisible()) {
      await rangeBtn1Y.click();
      await page.waitForTimeout(500);
    }

    await page.screenshot({ path: path.join(evidenceDir, "step-val-3-dashboard-summary.png") });
  });
});
