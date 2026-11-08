/**
 * Utility for polling historical NAV availability with backoff/interval and timeout limits.
 */

export interface PollingConfig {
  intervalMs?: number;
  maxDurationMs?: number;
  checkFn: () => Promise<boolean>;
  onAttempt?: (attempt: number) => void;
}

export async function pollNavHistory({
  intervalMs = 2000,
  maxDurationMs = 30000,
  checkFn,
  onAttempt,
}: PollingConfig): Promise<boolean> {
  const startTime = Date.now();
  let attempt = 0;

  while (Date.now() - startTime < maxDurationMs) {
    attempt += 1;
    onAttempt?.(attempt);

    const available = await checkFn();
    if (available) {
      return true;
    }

    // Wait for interval
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  throw new Error("Historical data fetch timed out. Please try again later.");
}

