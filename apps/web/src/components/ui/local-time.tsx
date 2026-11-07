"use client";

import * as React from "react";

const emptySubscribe = () => () => {};

export interface LocalTimeProps {
  /** Timestamp in epoch milliseconds, ISO string, or Date object. */
  timestamp?: number | string | Date | null;
  /** Placeholder rendered on server and initial client render before mount. */
  placeholder?: string;
  /** Formatting options for Intl.DateTimeFormat. */
  formatOptions?: Intl.DateTimeFormatOptions;
  /** Explicit BCP 47 locale (defaults to client locale or en-IN). */
  locale?: string;
  /** Additional CSS class names. */
  className?: string;
}

export function LocalTime({
  timestamp,
  placeholder = "—",
  formatOptions = {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  },
  locale,
  className,
}: LocalTimeProps): React.JSX.Element {
  // useSyncExternalStore guarantees isMounted is false on server AND during initial client hydration,
  // transitioning to true strictly after client mount commit with zero hydration mismatch.
  const isMounted = React.useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  if (!isMounted || !timestamp) {
    return <time className={className}>{placeholder}</time>;
  }

  const date =
    typeof timestamp === "object" && timestamp instanceof Date
      ? timestamp
      : new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return <time className={className}>{placeholder}</time>;
  }

  const isoString = date.toISOString();
  const formatted = date.toLocaleTimeString(locale, formatOptions);

  return (
    <time dateTime={isoString} className={className}>
      {formatted}
    </time>
  );
}

