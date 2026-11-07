import { describe, expect, it } from "vitest";
import { sanitizeRedirectUrl } from "./url";

describe("sanitizeRedirectUrl open-redirect safety", () => {
  it("defaults to /dashboard when input is empty or nullish", () => {
    expect(sanitizeRedirectUrl(null)).toBe("/dashboard");
    expect(sanitizeRedirectUrl(undefined)).toBe("/dashboard");
    expect(sanitizeRedirectUrl("")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("   ")).toBe("/dashboard");
  });

  it("permits safe root-relative application paths", () => {
    expect(sanitizeRedirectUrl("/dashboard")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("/dashboard/funds?sort=nav")).toBe("/dashboard/funds?sort=nav");
    expect(sanitizeRedirectUrl("/settings/security")).toBe("/settings/security");
  });

  it("neutralizes protocol-relative attempts", () => {
    expect(sanitizeRedirectUrl("//attacker.com")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("//attacker.com/evil")).toBe("/dashboard");
  });

  it("neutralizes absolute URLs with external protocols", () => {
    expect(sanitizeRedirectUrl("https://attacker.com")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("http://evil.com/phish")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("javascript:alert(1)")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("data:text/html,evil")).toBe("/dashboard");
  });

  it("neutralizes backslash evasion tricks", () => {
    expect(sanitizeRedirectUrl("/\\attacker.com")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("/dashboard\\evil")).toBe("/dashboard");
  });

  it("neutralizes paths containing carriage returns or control characters", () => {
    expect(sanitizeRedirectUrl("/dashboard\r\nattacker.com")).toBe("/dashboard");
    expect(sanitizeRedirectUrl("/dashboard\tattacker.com")).toBe("/dashboard");
  });
});

