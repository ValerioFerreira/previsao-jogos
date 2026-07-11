// Rastreamento de afiliado/influenciador (?ref=código) + portal do afiliado.
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

export const affiliatesApi = {
  me: () => authFetch<AffiliatePortalStats>("/affiliates/me"),
};
