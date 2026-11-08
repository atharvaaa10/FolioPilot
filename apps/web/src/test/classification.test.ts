import { describe, expect, it } from "vitest";
import * as fs from "fs";
import * as path from "path";
import { VALID_ASSET_CLASSES } from "@/lib/targets";
import { getAssetClassBadge } from "@/lib/format";

describe("Classification Consistency", () => {
  it("matches backend canonical classification.json", () => {
    // Navigate from apps/web/src/test up to docs/classification.json
    const jsonPath = path.resolve(__dirname, "../../../../docs/classification.json");
    expect(fs.existsSync(jsonPath)).toBe(true);

    const raw = fs.readFileSync(jsonPath, "utf-8");
    const data = JSON.parse(raw) as {
      valid_asset_classes: string[];
      classifications: { asset_class: string; sub_category: string | null }[];
    };

    // 1. Verify valid asset classes match exactly
    const sortedFrontendClasses = [...VALID_ASSET_CLASSES].sort();
    const sortedBackendClasses = [...data.valid_asset_classes].sort();
    expect(sortedFrontendClasses).toEqual(sortedBackendClasses);

    // 2. Verify all asset classes have a defined badge style
    for (const assetClass of data.valid_asset_classes) {
      const badge = getAssetClassBadge(assetClass);
      expect(badge.label.toLowerCase()).toBe(assetClass.toLowerCase());
      expect(badge.className).toBeTruthy();
    }

    // 3. Verify canonical classification list is non-empty and well-formed
    expect(data.classifications.length).toBeGreaterThan(50);
    for (const item of data.classifications) {
      expect(data.valid_asset_classes).toContain(item.asset_class);
    }
  });
});

