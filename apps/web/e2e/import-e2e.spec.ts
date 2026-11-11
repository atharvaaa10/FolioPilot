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
      // Ignore expected 4xx browser network status messages
      if (
        text.includes("401 (Unauthorized)") ||
        text.includes("409 (Conflict)") ||
        text.includes("404 (Not Found)") ||
        text.includes("422 (Unprocessable Entity)") ||
        text.includes("IMPORT_FILE_INVALID") ||
        text.includes("IMPORT_HAS_ERRORS") ||
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

test.describe("Transaction Excel Import End-to-End Flow", () => {
  test("template download, invalid file guard, with-errors skip flow, worked-example exact math, duplicate detection, and undo", async ({
    page,
  }) => {
    attachErrorGuards(page);

    const timestamp = Date.now();
    const testEmail = `import_investor_${timestamp}@example.com`;
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

    // --- STEP 2: Navigate to /portfolios and create a portfolio ---
    await page.click('a[href="/portfolios"]');
    await page.waitForURL("**/portfolios", { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("Portfolios");

    await page.click('button:has-text("Create Portfolio")');
    await page.fill("#portfolio-name", "Import Test Portfolio");
    await page.fill("#portfolio-desc", "Portfolio for testing Excel transactions import");
    await page.click('button[type="submit"]:has-text("Create Portfolio")');

    await expect(page.locator('a:has-text("Import Test Portfolio")')).toBeVisible({ timeout: 10000 });
    await page.click('a:has-text("Import Test Portfolio")');
    await page.waitForURL("**/portfolios/*", { timeout: 15000 });
    await expect(page.locator("h1")).toContainText("Import Test Portfolio");

    // --- STEP 3: Template Download Verification ---
    await page.click('button:has-text("Import Excel")');
    await expect(page.locator('h2:has-text("Import Transactions from Excel")')).toBeVisible();

    const downloadPromise = page.waitForEvent("download");
    await page.click('button:has-text("Download Template (.xlsx)")');
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("foliopilot-transactions-template.xlsx");
    await page.screenshot({ path: path.join(evidenceDir, "step-import-1-template-download.png") });

    // --- STEP 4: Invalid File Guard ---
    const invalidFilePath = path.join(evidenceDir, "invalid-not-a-zip.xlsx");
    fs.writeFileSync(invalidFilePath, "This is plain text and definitely not a valid zip or xlsx file.");

    const fileInput = page.locator("#file-input");
    await fileInput.setInputFiles(invalidFilePath);
    await page.click('button:has-text("Analyze & Preview")');

    // Expect error alert in UI
    await expect(
      page.locator("text=/File is not a valid zip archive|IMPORT_FILE_INVALID|Failed to analyze import file/i")
    ).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: path.join(evidenceDir, "step-import-2-invalid-file.png") });

    // Close and reopen dialog
    await page.click('button:has-text("Cancel")');

    // --- STEP 5: Upload with-errors.xlsx & Skip Invalid Flow ---
    const withErrorsPath = path.resolve(__dirname, "../../api/tests/fixtures/imports/with-errors.xlsx");
    expect(fs.existsSync(withErrorsPath)).toBe(true);

    await page.click('button:has-text("Import Excel")');
    await fileInput.setInputFiles(withErrorsPath);
    await page.click('button:has-text("Analyze & Preview")');

    // Preview table loads
    await expect(page.locator("text=Total Rows")).toBeVisible({ timeout: 15000 });
    await expect(page.locator("text=Errors")).toBeVisible();

    // Verify commit button is disabled
    const importBtn = page.locator('button:has-text("Import")').filter({ hasText: /Transactions/ });
    await expect(importBtn).toBeDisabled();

    // Check "Skip invalid rows"
    await page.check("#skip-invalid-checkbox");
    await expect(importBtn).toBeEnabled();

    // Click Import
    await importBtn.click();
    // Confirm in confirmation modal if shown
    const confirmCommitBtn = page.locator('button:has-text("Confirm & Commit")');
    if (await confirmCommitBtn.isVisible()) {
      await confirmCommitBtn.click();
    }

    // Wait for success / result step or modal dismissal
    await expect(page.locator("text=/Successfully imported|Done/i")).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(evidenceDir, "step-import-3-with-errors-committed.png") });

    // Click "Done" to close dialog
    const doneBtn = page.locator('button:has-text("Done")');
    if (await doneBtn.isVisible()) {
      await doneBtn.click();
    }

    // --- STEP 6: Worked Example in Fresh Portfolio for Exact Holdings Verification ---
    await page.click('a[href="/portfolios"]');
    await page.waitForURL("**/portfolios", { timeout: 15000 });

    await page.click('button:has-text("Create Portfolio")');
    await page.fill("#portfolio-name", "Worked Example Portfolio");
    await page.fill("#portfolio-desc", "Portfolio verifying exact 120 units and 6400 cost basis");
    await page.click('button[type="submit"]:has-text("Create Portfolio")');

    await expect(page.locator('a:has-text("Worked Example Portfolio")')).toBeVisible({ timeout: 10000 });
    await page.click('a:has-text("Worked Example Portfolio")');
    await page.waitForURL("**/portfolios/*", { timeout: 15000 });

    const workedExamplePath = path.resolve(__dirname, "../../api/tests/fixtures/imports/worked-example.xlsx");
    expect(fs.existsSync(workedExamplePath)).toBe(true);

    await page.click('button:has-text("Import Excel")');
    await page.locator("#file-input").setInputFiles(workedExamplePath);
    await page.click('button:has-text("Analyze & Preview")');

    await expect(page.locator("text=Total Rows")).toBeVisible({ timeout: 15000 });
    await expect(page.locator("text=Will Import")).toBeVisible();

    const commitWorkedExampleBtn = page.locator('button:has-text("Import 3 Transactions")');
    await expect(commitWorkedExampleBtn).toBeEnabled();
    await commitWorkedExampleBtn.click();

    if (await page.locator('button:has-text("Confirm & Commit")').isVisible()) {
      await page.locator('button:has-text("Confirm & Commit")').click();
    }

    await expect(page.locator("text=/Successfully imported 3 transactions|Done/i")).toBeVisible({ timeout: 15000 });
    await page.screenshot({ path: path.join(evidenceDir, "step-import-4-worked-example-committed.png") });

    if (await page.locator('button:has-text("Done")').isVisible()) {
      await page.locator('button:has-text("Done")').click();
    }

    // Verify exact portfolio holdings on the page:
    // Units: 120, Cost Basis: ₹6,400.00, Avg Cost: ₹53.33 (or 53.3333)
    await expect(page.locator("body")).toContainText("Parag Parikh Flexi Cap Fund");
    await expect(page.locator("body")).toContainText("120");
    await expect(page.locator("body")).toContainText("6,400");
    await expect(page.locator("body")).toContainText("53.33");
    await page.screenshot({ path: path.join(evidenceDir, "step-import-5-holdings-verified.png") });

    // --- STEP 7: Re-upload worked-example.xlsx for Duplicate Detection ---
    await page.click('button:has-text("Import Excel")');
    await page.locator("#file-input").setInputFiles(workedExamplePath);
    await page.click('button:has-text("Analyze & Preview")');

    await expect(page.locator("text=Total Rows")).toBeVisible({ timeout: 15000 });
    // All 3 rows should be marked as duplicate
    await expect(page.locator("text=3 Duplicate")).toBeVisible();
    await expect(page.locator("text=0 Will Import")).toBeVisible();

    // Import button must be disabled because will_import == 0
    const reuploadImportBtn = page.locator('button:has-text("Import")').filter({ hasText: /Transactions/ });
    await expect(reuploadImportBtn).toBeDisabled();
    await page.screenshot({ path: path.join(evidenceDir, "step-import-6-duplicate-detection.png") });

    // Close preview
    await page.click('button:has-text("Cancel")');

    // --- STEP 8: Undo Import Batch ---
    // Locate the committed batch in Import History table
    const historySection = page.locator("text=Import History").locator("xpath=ancestor::div[contains(@class, 'rounded-xl')]");
    await expect(historySection).toBeVisible();
    await expect(historySection.locator('text="worked-example.xlsx"')).toBeVisible();

    const undoBtn = historySection.locator('button:has-text("Undo")').first();
    await expect(undoBtn).toBeVisible();
    await undoBtn.click();

    // Undo confirmation dialog
    await expect(page.locator('h2:has-text("Undo Import Batch")')).toBeVisible();
    await page.click('button:has-text("Confirm Undo")');

    // Verify status transitions to Undone
    await expect(historySection.locator('text="Undone"')).toBeVisible({ timeout: 15000 });

    // Verify holdings return to empty
    await expect(page.locator("text=No holdings recorded yet")).toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: path.join(evidenceDir, "step-import-7-undone.png") });
  });
});
