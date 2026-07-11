// Chamadas autenticadas dos domínios de monetização (pagamentos, análise, apostas, legal).
import { authFetch } from "@/lib/authApi";

// ---------------- pagamentos / carteira ----------------
export type CreditPackage = {
  id: string;
  name: string;
  credits: number;
  price_brl: string;
  bonus_credits: number;
  total_credits: number;
  featured_badge?: "mais_vendido" | "melhor_oferta" | "oferta_limitada" | null;
};

export type CouponPreview = {
  coupon_id: string;
  code: string;
  discount_type: string | null;
  original_amount_brl: string;
  final_amount_brl: string;
  bonus_credits: number;
};

export type Banner = { id: string; title: string; body: string | null; type: string };

export type Transaction = {
  id: string;
  type: string;
  status: string;
  amount: string;
  balance_after: string;
  reserved_after: string;
  description: string | null;
  reference_type: string | null;
  created_at: string;
};

export const paymentsApi = {
  packages: () => authFetch<CreditPackage[]>("/payments/packages"),
  recommended: () => authFetch<CreditPackage | null>("/payments/packages/recommended"),
  checkout: (body: { package_id?: string; credits?: number; coupon_code?: string }) =>
    authFetch<{ order_id: string; provider: string; status: string; amount_brl: string; credits: number; checkout: Record<string, unknown> }>(
      "/payments/checkout",
      { method: "POST", body: JSON.stringify(body) },
    ),
  mockConfirm: (orderId: string) =>
    authFetch<{ order_id: string; status: string; available_balance: string }>(
      `/payments/mock/confirm/${orderId}`,
      { method: "POST" },
    ),
};

export const walletApiFull = {
  transactions: (limit = 50, offset = 0, filters?: { type?: string; status?: string }) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (filters?.type) params.set("type", filters.type);
    if (filters?.status) params.set("status", filters.status);
    return authFetch<{ items: Transaction[]; total: number; limit: number; offset: number }>(
      `/wallet/transactions?${params.toString()}`,
    );
  },
};

export type OrderListItem = {
  order_id: string;
  provider: string;
  method: string | null;
  status: string;
  amount_brl: string;
  credits: number;
  checkout: Record<string, unknown> | null;
  invoice_url: string | null;
  invoice_status: string | null;
  created_at: string;
  paid_at: string | null;
};

export const ordersApi = {
  mine: () => authFetch<OrderListItem[]>("/payments/orders"),
  pending: () => authFetch<OrderListItem[]>("/payments/orders/pending"),
};

export const promotionsApi = {
  validateCoupon: (body: { code: string; amount_brl: string | number; credits: number; package_id?: string }) =>
    authFetch<CouponPreview>("/promotions/coupons/validate", { method: "POST", body: JSON.stringify(body) }),
};

export const bannersApi = {
  active: () => authFetch<{ items: Banner[] }>("/banners/active"),
};

// ---------------- análise ----------------
export type AnalysisResponse = {
  id: string;
  type: string;
  status: string;
  home_team: string;
  away_team: string;
  tournament: string;
  fixture_id: number | null;
  algo_version: string;
  created_at: string;
  credits_consumed: number;
  credits_reserved: number;
  available_balance: string;
  snapshot: Record<string, unknown>;
};

export type AnalysisSummary = {
  id: string;
  type: string;
  status: string;
  home_team: string;
  away_team: string;
  tournament: string;
  fixture_id: number | null;
  algo_version: string;
  created_at: string;
};

export const analysisApi = {
  create: (body: { home_team: string; away_team: string; tournament: string; neutral: boolean; type: string; fixture_id?: number | null }) =>
    authFetch<AnalysisResponse>("/analysis", { method: "POST", body: JSON.stringify(body) }),
  list: (limit = 20, offset = 0) =>
    authFetch<{ items: AnalysisSummary[]; total: number; limit: number; offset: number }>(`/analysis?limit=${limit}&offset=${offset}`),
  get: (id: string) => authFetch<AnalysisResponse>(`/analysis/${id}`),
};

// ---------------- apostas ----------------
export type MarketOption = { market_key: string; group: string; label: string; selection: string; odd: number };
export type BetSelection = { market_key: string; label: string; selection: string; odd: number };
export type BetResponse = {
  id: string;
  analysis_id: string;
  status: string;
  combined_odd: string;
  auto_selected: boolean;
  fixture_id: number | null;
  match_datetime: string | null;
  created_at: string;
  selections: BetSelection[];
};

export const betsApi = {
  markets: (analysisId: string) =>
    authFetch<{ analysis_id: string; home_team: string; away_team: string; max_combined_odd: number; options: MarketOption[] }>(
      `/bets/markets/${analysisId}`,
    ),
  preview: (analysisId: string, market_keys: string[]) =>
    authFetch<{ selections: BetSelection[]; combined_odd: number; valid: boolean; exceeds_cap: boolean; auto: boolean; max_combined_odd: number }>(
      `/bets/preview/${analysisId}`,
      { method: "POST", body: JSON.stringify({ market_keys }) },
    ),
  create: (analysisId: string, market_keys: string[]) =>
    authFetch<BetResponse>(`/bets/${analysisId}`, { method: "POST", body: JSON.stringify({ market_keys }) }),
  list: (limit = 20, offset = 0) =>
    authFetch<{ items: BetResponse[]; total: number; limit: number; offset: number }>(`/bets?limit=${limit}&offset=${offset}`),
};

// ---------------- documentos legais ----------------
export type LegalDoc = { id: string; type: string; version: number; title: string; published_at: string | null };

export const legalApi = {
  documents: () => authFetch<LegalDoc[]>("/legal/documents"),
  document: (type: string) => authFetch<LegalDoc & { body_md: string }>(`/legal/documents/${type}`),
  pending: () => authFetch<LegalDoc[]>("/legal/pending"),
  accept: (document_ids: string[]) =>
    authFetch<{ accepted: string[]; message: string }>("/legal/accept", { method: "POST", body: JSON.stringify({ document_ids }) }),
};
