export interface Metric { value: number; previous: number | null }

export interface DayPoint { date: string; booked: number; cancelled: number; no_show: number; revenue_paise: number; refunds_paise: number }

export interface Breakdown {
  key: string;
  label: string;
  appointments: number;
  completed: number;
  cancelled: number;
  no_show: number;
  revenue_paise: number;
  booked_minutes: number;
  available_minutes: number | null;
  utilization: number | null;
}

export interface HeatCell { weekday: number; hour: number; appointments: number }

export interface Dashboard {
  from_date: string;
  to_date: string;
  timezone: string;
  scope: "organization" | "professional";
  kpis: Record<string, Metric>;
  series: DayPoint[];
  by_service: Breakdown[];
  by_professional: Breakdown[];
  by_branch: Breakdown[];
  by_source: Breakdown[];
  payment_methods: Breakdown[];
  heatmap: HeatCell[];
  today: { total: number; upcoming: number; checked_in: number; completed: number; no_show: number; awaiting_payment: number };
  attention: Record<string, number>;
}

export interface ReportColumn { key: string; label: string; type: "text" | "int" | "money" | "percent" | "date" | "datetime" | "time" }
export interface ReportInfo { key: string; title: string; description: string; columns: ReportColumn[]; contains_personal_data: boolean; can_export: boolean }
export interface ReportResult {
  key: string;
  title: string;
  columns: ReportColumn[];
  rows: Record<string, string | number | null>[];
  totals: Record<string, number>;
  total_rows: number;
  page: number;
  page_size: number;
  truncated: boolean;
  from_date: string;
  to_date: string;
}

export interface AnalyticsFilters { from?: string; to?: string; branch_id?: string; professional_id?: string; service_id?: string }
