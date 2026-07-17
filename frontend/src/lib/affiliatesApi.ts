// Rastreamento de parceiro (?ref=código) + solicitação de parceria + portal do parceiro.
// Nomes internos seguem em inglês ("affiliate") — o rótulo em português é só na UI.
import { authFetch } from "@/lib/authApi";

const ANON_KEY = "apostai_anon_id";
const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

function getAnonId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(ANON_KEY);
  if (!id) {
    id = `anon_${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    localStorage.setItem(ANON_KEY, id);
  }
  return id;
}

/** Chamar uma vez ao carregar qualquer página pública: captura ?ref= e registra o clique. */
export function captureReferralFromUrl() {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  const code = params.get("ref");
  if (!code) return;
  const anon_id = getAnonId();
  fetch(`${API_URL}/affiliates/track`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, anon_id }),
  }).catch(() => { /* silencioso — não deve travar navegação */ });
}

/** Chamar quando uma sessão autenticada é estabelecida (login/cadastro concluído). */
export function attachSignupIfReferred() {
  if (typeof window === "undefined") return;
  const anon_id = localStorage.getItem(ANON_KEY);
  if (!anon_id) return;
  authFetch("/affiliates/attach", { method: "POST", body: JSON.stringify({ anon_id }) }).catch(() => {});
}

export type AffiliatePortalStats = {
  code: string;
  link: string;
  clicks: number;
  signups: number;
  buyers: number;
  revenue_brl: string;
  commission_due_brl: string;
  commission_paid_brl: string;
};

export type TimeseriesPoint = {
  bucket: string;
  clicks: number;
  conversions: number;
  revenue_brl: string;
  commission_brl: string;
};

export type TimeseriesResponse = {
  granularity: string;
  items: TimeseriesPoint[];
};

export type PartnerApplication = {
  full_name: string;
  cpf: string;
  email: string;
  phone: string;
  payment_type: "pf" | "pj";
  discount_pct: number;
  code_prefix?: string;
};

export type CodeSuggestion = { prefix: string; code: string };

export const affiliatesApi = {
  me: () => authFetch<AffiliatePortalStats>("/affiliates/me"),
  apply: (data: PartnerApplication) =>
    fetch(`${API_URL}/affiliates/apply`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    }).then(async (res) => {
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Erro ${res.status}`);
      }
      return res.json() as Promise<{ ok: boolean; message: string }>;
    }),
  suggestCode: (full_name: string, discount_pct: number) =>
    fetch(`${API_URL}/affiliates/suggest-code?${new URLSearchParams({ full_name, discount_pct: String(discount_pct) })}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`Erro ${res.status}`);
        return res.json() as Promise<CodeSuggestion>;
      }),
  portalMe: () => authFetch<AffiliatePortalStats>("/affiliates/portal/me"),
  portalTimeseries: (granularity: "day" | "month" = "day") =>
    authFetch<TimeseriesResponse>(`/affiliates/portal/timeseries?granularity=${granularity}`),
};
