/**
 * Open-redirect safe URL sanitizer.
 * Guarantees redirect destinations stay within application origin.
 */

export function sanitizeRedirectUrl(next: string | null | undefined): string {
  if (!next) {
    return "/dashboard";
  }

  const trimmed = next.trim();

  // Reject protocol-relative (//), external schemes (http:, javascript:), backslashes anywhere, or control characters
  if (
    !trimmed.startsWith("/") ||
    trimmed.startsWith("//") ||
    trimmed.includes("\\") ||
    trimmed.includes(":") ||
    /[\r\n\t]/.test(trimmed)
  ) {
    return "/dashboard";
  }

  return trimmed;
}
