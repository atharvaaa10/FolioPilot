/**
 * TypeScript interface definitions for Funds and NAV master data.
 */

export interface FundSearchItem {
  id: string;
  scheme_code: number;
  name: string;
  amc: string;
  category_raw: string;
  asset_class: string;
  sub_category: string | null;
  plan_type: string;
  option_type: string;
  latest_nav: string | number | null;
  latest_nav_date: string | null;
  is_active: boolean;
  is_tracked: boolean;
}

export interface FundSearchResponse {
  items: FundSearchItem[];
  has_more: boolean;
}

export interface FundDetailResponse {
  id: string;
  scheme_code: number;
  isin_growth: string | null;
  isin_reinvest: string | null;
  name: string;
  amc: string;
  scheme_type_raw: string | null;
  category_raw: string;
  asset_class: string;
  sub_category: string | null;
  classification_source: string;
  plan_type: string;
  option_type: string;
  latest_nav: string | number | null;
  latest_nav_date: string | null;
  is_active: boolean;
  is_tracked: boolean;
}

export interface NavPoint {
  date: string;
  nav: string | number;
}

export interface FundNavHistoryResponse {
  scheme_code: number;
  name: string;
  history_available: boolean;
  points: NavPoint[];
}

export interface TrackFundResponse {
  scheme_code: number;
  status: "queued" | "already_tracked";
}

export interface NavStatusResponse {
  last_run_time: string | null;
  last_run_status: string | null;
  last_success_time: string | null;
  schemes_parsed: number;
  funds_created: number;
  funds_updated: number;
  nav_rows_written: number;
  is_stale: boolean;
}

