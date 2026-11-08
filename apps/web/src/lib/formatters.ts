/** Utility formatters for NAV, dates, and badge styling. */

export interface BadgeStyle {
  label: string;
  className: string;
}

export function formatNav(nav: number | string | null | undefined): string {
  if (nav === null || nav === undefined || nav === "") {
    return "—";
  }
  const num = typeof nav === "number" ? nav : parseFloat(nav);
  if (Number.isNaN(num)) {
    return "—";
  }
  return `₹${num.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  })}`;
}

export function formatDateString(dateStr: string | null | undefined): string {
  if (!dateStr) {
    return "—";
  }
  // Pure date strings like "2026-11-06" parsed as calendar dates without timezone skew
  const parts = dateStr.split("-");
  if (parts.length === 3 && parts[0] && parts[1] && parts[2]) {
    const year = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10) - 1;
    const day = parseInt(parts[2], 10);
    const months = [
      "Jan",
      "Feb",
      "Mar",
      "Apr",
      "May",
      "Jun",
      "Jul",
      "Aug",
      "Sep",
      "Oct",
      "Nov",
      "Dec",
    ];
    if (month >= 0 && month < 12 && !Number.isNaN(year) && !Number.isNaN(day)) {
      return `${day.toString().padStart(2, "0")} ${months[month]} ${year}`;
    }
  }
  return dateStr;
}

export function getAssetClassBadge(assetClass: string): BadgeStyle {
  const normalized = assetClass.toLowerCase();
  switch (normalized) {
    case "equity":
      return {
        label: "Equity",
        className:
          "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
      };
    case "debt":
      return {
        label: "Debt",
        className:
          "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/20",
      };
    case "gold":
      return {
        label: "Gold",
        className:
          "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
      };
    case "hybrid":
      return {
        label: "Hybrid",
        className:
          "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/20",
      };
    default:
      return {
        label: "Other",
        className:
          "bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 border-zinc-500/20",
      };
  }
}

export function getPlanBadge(plan: string): BadgeStyle {
  const normalized = plan.toLowerCase();
  switch (normalized) {
    case "direct":
      return {
        label: "Direct",
        className:
          "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20",
      };
    case "regular":
      return {
        label: "Regular",
        className:
          "bg-slate-500/10 text-slate-600 dark:text-slate-400 border-slate-500/20",
      };
    default:
      return {
        label: "Unknown",
        className:
          "bg-zinc-500/10 text-zinc-500 dark:text-zinc-400 border-zinc-500/20",
      };
  }
}

export function getOptionBadge(option: string): BadgeStyle {
  const normalized = option.toLowerCase();
  switch (normalized) {
    case "growth":
      return {
        label: "Growth",
        className:
          "bg-teal-500/10 text-teal-600 dark:text-teal-400 border-teal-500/20",
      };
    case "idcw":
      return {
        label: "IDCW",
        className:
          "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
      };
    default:
      return {
        label: "Unknown",
        className:
          "bg-zinc-500/10 text-zinc-500 dark:text-zinc-400 border-zinc-500/20",
      };
  }
}
