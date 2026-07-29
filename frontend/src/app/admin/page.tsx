"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, Shield, Ban, CheckCircle2, Coins, Plus, X } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { adminApi, type AdminUser, type AuditEntry } from "@/lib/adminApi";
import { api, type UpcomingFixture } from "@/lib/api";
import { legalApi, type LegalDoc } from "@/lib/monetizationApi";
import { MatchPickerModal, type PickerFixture } from "@/components/platform/MatchPickerModal";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from "recharts";


function fmt(d: string) { return new Date(d).toLocaleString("pt-BR"); }

// ---------- componentes genéricos de UI (modal/campo) ----------
function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; wide?: boolean }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className={`w-full ${wide ? "max-w-2xl" : "max-w-md"} max-h-[85vh] overflow-y-auto rounded-2xl border border-border bg-card shadow-2xl p-5`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground p-1 rounded-md hover:bg-muted transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ConfirmModal({ state, onClose }: { state: { message: string; onConfirm: () => void } | null; onClose: () => void }) {
  return (
    <Modal open={!!state} onClose={onClose} title="Confirmar ação">
      {state && (
        <>
          <p className="text-sm text-muted-foreground mb-4">{state.message}</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>Cancelar</Button>
            <Button type="button" variant="destructive" size="sm" onClick={() => { state.onConfirm(); onClose(); }}>Confirmar</Button>
          </div>
        </>
      )}
    </Modal>
  );
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={className}>
      <Label className="text-xs text-muted-foreground mb-1 block">{label}</Label>
      {children}
    </div>
  );
}

// ---------- gráfico simples de receita por período (dashboard) ----------
function RevenueChart({ rev }: { rev: Record<string, string> | undefined }) {
  const [period, setPeriod] = useState<"today" | "month" | "year">("month");
  const data = [
    { key: "today" as const, label: "Hoje", value: Number(rev?.today_brl ?? 0) },
    { key: "month" as const, label: "Mês", value: Number(rev?.month_brl ?? 0) },
    { key: "year" as const, label: "Ano", value: Number(rev?.year_brl ?? 0) },
  ];
  const max = Math.max(1, ...data.map((d) => d.value));
  const active = data.find((d) => d.key === period)!;
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm font-medium">Receita por período</div>
        <select
          className="border rounded-md px-2 py-1.5 text-xs bg-background"
          value={period}
          onChange={(e) => setPeriod(e.target.value as "today" | "month" | "year")}
        >
          <option value="today">Hoje</option>
          <option value="month">Mês</option>
          <option value="year">Ano</option>
        </select>
      </div>
      <div className="text-2xl font-bold mb-3">R$ {active.value.toFixed(2)}</div>
      <div className="flex items-end gap-6 h-32">
        {data.map((d) => (
          <div key={d.key} className="flex-1 flex flex-col items-center gap-1.5">
            <div className={`w-full rounded-t-md transition-all ${d.key === period ? "bg-primary" : "bg-muted"}`}
                 style={{ height: `${Math.max(6, (d.value / max) * 96)}px` }} />
            <div className="text-[11px] text-muted-foreground">{d.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

type PartnerMetric = "revenue_brl" | "profit_brl" | "payments_brl";
const PARTNER_METRICS: { key: PartnerMetric; label: string }[] = [
  { key: "revenue_brl", label: "Faturamento" },
  { key: "profit_brl", label: "Lucro" },
  { key: "payments_brl", label: "Pagamentos" },
];

// ---------- gráfico de barras: faturamento/lucro/pagamentos por parceiro ----------
function PartnerRevenueChart({ items }: { items: Record<string, unknown>[] }) {
  const [metric, setMetric] = useState<PartnerMetric>("revenue_brl");
  const [topN, setTopN] = useState("10");
  const n = Math.max(1, Number(topN) || 10);

  const data = [...items]
    .map((p) => ({ name: String(p.name), value: Number(p[metric] ?? 0) }))
    .sort((a, b) => b.value - a.value)
    .slice(0, n);

  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <div className="text-sm font-medium">Faturamento/lucro/pagamentos por parceiro</div>
        <div className="flex gap-2 items-center">
          <select className="border rounded-md px-2 py-1.5 text-xs bg-background" value={metric} onChange={(e) => setMetric(e.target.value as PartnerMetric)}>
            {PARTNER_METRICS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
          <label className="text-xs text-muted-foreground flex items-center gap-1">
            Top
            <Input className="w-16 h-8" type="number" min="1" value={topN} onChange={(e) => setTopN(e.target.value)} />
          </label>
        </div>
      </div>
      {data.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nenhum parceiro com dados ainda.</p>
      ) : (
        <div style={{ width: "100%", height: Math.max(200, data.length * 36) }}>
          <ResponsiveContainer>
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => `R$ ${Number(v).toFixed(0)}`} fontSize={11} />
              <YAxis type="category" dataKey="name" width={120} fontSize={11} />
              <RTooltip formatter={(v: number) => [`R$ ${Number(v).toFixed(2)}`, PARTNER_METRICS.find((m) => m.key === metric)?.label]} />
              <Bar dataKey="value" fill="var(--primary)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function AdminPage() {
  const { user, loading } = useAuth();
  const { toast } = useToast();
  const router = useRouter();
  const isOwner = user && (user.role === "owner" || user.email === "valerioeducfin@gmail.com");
  const isManager = user && user.role === "manager";
  const isAdmin = isOwner || isManager;

  const [testPassword, setTestPassword] = useState("");
  const [testAccountBusy, setTestAccountBusy] = useState(false);
  const [testAccountMsg, setTestAccountMsg] = useState<string | null>(null);

  const [users, setUsers] = useState<AdminUser[]>([]);

  const [q, setQ] = useState("");
  const [payments, setPayments] = useState<Record<string, unknown>[]>([]);
  const [promos, setPromos] = useState<Record<string, unknown>[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [dashboard, setDashboard] = useState<Record<string, unknown> | null>(null);
  const [coupons, setCoupons] = useState<Record<string, unknown>[]>([]);
  const [couponAnalytics, setCouponAnalytics] = useState<Record<string, unknown>[]>([]);
  const [packages, setPackages] = useState<Record<string, unknown>[]>([]);
  const [affiliates, setAffiliates] = useState<Record<string, unknown>[]>([]);
  const [banners, setBanners] = useState<Record<string, unknown>[]>([]);
  const [campaigns, setCampaigns] = useState<Record<string, unknown>[]>([]);
  const [deepAnalyses, setDeepAnalyses] = useState<Record<string, unknown>[]>([]);
  const [demoUsage, setDemoUsage] = useState<Record<string, unknown>[]>([]);
  const [settings, setSettings] = useState<Record<string, unknown>[]>([]);
  const [legalDocs, setLegalDocs] = useState<LegalDoc[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [legalMsg, setLegalMsg] = useState<string | null>(null);

  // States for MatchPickerModal
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [allCompetitions, setAllCompetitions] = useState<{ selecao: string[]; clube: string[] }>({ selecao: [], clube: [] });
  const [pickerDeepAnalysisOpen, setPickerDeepAnalysisOpen] = useState(false);
  const [featuredMatches, setFeaturedMatches] = useState<{ id: string; fixture_id: number; scope: string; sort_order: number; fixture: UpcomingFixture | null }[]>([]);
  const [pickerFeaturedOpen, setPickerFeaturedOpen] = useState(false);
  const [sharedAnalyses, setSharedAnalyses] = useState<{ id: string; token: string; home_team: string; away_team: string; scope: string; tournament: string; match_date: string | null; active: boolean; created_at: string }[]>([]);
  const [pickerShareOpen, setPickerShareOpen] = useState(false);

  const [newPromo, setNewPromo] = useState({ code: "", name: "", type: "refund_if_lose" });
  const [newCoupon, setNewCoupon] = useState({
    promotion_id: "", code: "", discount_type: "percentage", discount_value: "10",
    min_purchase_brl: "", first_purchase_only: false, description: "", valid_days: "30",
  });
  const [newPackage, setNewPackage] = useState({ name: "", credits: "10", price_brl: "10.00", bonus_credits: "0" });
  const [newAffiliate, setNewAffiliate] = useState({
    name: "", code: "", commission_pct: "10", contact_email: "", contact_phone: "",
    cpf: "", payment_type: "", discount_pcts: "",
  });
  const [promoSection, setPromoSection] = useState<"promocoes" | "cupons" | "pacotes" | "banners" | "campanhas">("promocoes");
  const [partnerFilter, setPartnerFilter] = useState("");
  const [partnerSearch, setPartnerSearch] = useState("");
  const [partnerSortRevenue, setPartnerSortRevenue] = useState<"none" | "desc" | "asc">("none");
  const [partnerDetailModal, setPartnerDetailModal] = useState<Record<string, unknown> | null>(null);
  const [payUserSearch, setPayUserSearch] = useState("");
  const [payDateFrom, setPayDateFrom] = useState("");
  const [payDateTo, setPayDateTo] = useState("");
  const [approveCodeDrafts, setApproveCodeDrafts] = useState<Record<string, string>>({});
  const [couponRequests, setCouponRequests] = useState<Record<string, unknown>[]>([]);
  const [pendingCounts, setPendingCounts] = useState<{ partner_applications: number; coupon_requests: number; total: number } | null>(null);
  const [newBanner, setNewBanner] = useState({ title: "", body: "", image_url: "", priority: "0", sort_order: "0" });
  const [newCampaign, setNewCampaign] = useState({ name: "", priority: "0" });
  const [newDeepAnalysis, setNewDeepAnalysis] = useState({ fixture_id: "", analyst_name: "", markdown_content: "" });
  const [newSetting, setNewSetting] = useState({ key: "", value: "" });
  const [attributionDays, setAttributionDays] = useState("30");

  // ---- estado dos modais ----
  const [confirmState, setConfirmState] = useState<{ message: string; onConfirm: () => void } | null>(null);
  const [grantModal, setGrantModal] = useState<AdminUser | null>(null);
  const [grantForm, setGrantForm] = useState({ amount: "10", reason: "cortesia" });
  const [editCouponModal, setEditCouponModal] = useState<Record<string, unknown> | null>(null);
  const [editCouponForm, setEditCouponForm] = useState({
    discount_type: "percentage", discount_value: "", min_purchase_brl: "", usage_limit: "", per_user_limit: "",
    valid_to: "", first_purchase_only: false, description: "", active: true,
  });
  const [editBannerModal, setEditBannerModal] = useState<Record<string, unknown> | null>(null);
  const [editBannerForm, setEditBannerForm] = useState({ title: "", body: "", image_url: "" });
  const [editLegalModal, setEditLegalModal] = useState<LegalDoc | null>(null);
  const [editLegalForm, setEditLegalForm] = useState({ title: "", body_md: "" });
  const [editLegalLoading, setEditLegalLoading] = useState(false);
  const [affPaymentModal, setAffPaymentModal] = useState<Record<string, unknown> | null>(null);
  const [affPaymentForm, setAffPaymentForm] = useState({ amount_brl: "0", method: "pix" });
  const [affPaymentsListModal, setAffPaymentsListModal] = useState<{ affiliate: Record<string, unknown>; items: Record<string, unknown>[] } | null>(null);
  const [campaignDashModal, setCampaignDashModal] = useState<Record<string, unknown> | null>(null);
  const [rejectModal, setRejectModal] = useState<Record<string, unknown> | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [pickerModal, setPickerModal] = useState<{ campaignId: string; kind: "banner" | "package" | "coupon" | "affiliate" } | null>(null);

  useEffect(() => { if (!loading && !isAdmin) router.replace("/"); }, [loading, isAdmin, router]);

  const loadUsers = useCallback(async (query = "") => {
    try { setUsers((await adminApi.users(query)).items); } catch (e) { setErr((e as Error).message); }
  }, []);

  const loadAll = useCallback(async () => {
    if (isOwner) {
      await loadUsers();
    }
    try {
      const promises: Promise<unknown>[] = [
        adminApi.promotions().then(r => setPromos(r.items)),
        adminApi.coupons().then(r => setCoupons(r.items)),
        adminApi.packages().then(r => setPackages(r.items)),
        adminApi.banners().then(r => setBanners(r.items)),
        adminApi.campaigns().then(r => setCampaigns(r.items)),
        adminApi.deepAnalyses().then(r => setDeepAnalyses(r.items)),
        adminApi.featuredMatches().then(r => setFeaturedMatches(r.items)),
        adminApi.sharedAnalyses().then(r => setSharedAnalyses(r.items)),
        api.upcomingFixtures().then(r => setUpcoming(r.fixtures)),
        Promise.all([api.teamIds("selecao"), api.teamIds("clube")]).then(([sel, clu]) => setTeamIds({ ...sel, ...clu })),
        Promise.all([api.teams("selecao"), api.teams("clube")]).then(([sel, clu]) => setAllCompetitions({ selecao: sel.tournaments, clube: clu.tournaments })),
      ];

      if (isOwner) {
        promises.push(
          adminApi.payments().then(r => setPayments(r.items)),
          adminApi.audit().then(r => setAudit(r.items)),
          adminApi.dashboard().then(r => setDashboard(r)),
          adminApi.couponAnalytics().then(r => setCouponAnalytics(r.items)),
          adminApi.affiliates().then(r => setAffiliates(r.items)),
          legalApi.documents().then(r => setLegalDocs(r)),
          adminApi.demoUsage().then(r => setDemoUsage(r.items)),
          adminApi.settings().then(r => setSettings(r.items)),
          loadPartnerRequests(),
        );
      }

      await Promise.all(promises);
    } catch (e) { setErr((e as Error).message); }
  }, [loadUsers, isOwner]);

  useEffect(() => { if (isAdmin) loadAll(); }, [isAdmin, loadAll]);

  useEffect(() => {
    const s = settings.find((s) => s.key === "affiliate_attribution_days");
    if (s) setAttributionDays(String((s.value as { days?: number } | null)?.days ?? "30"));
  }, [settings]);

  async function toggleBlock(u: AdminUser) {
    if (u.status === "blocked") await adminApi.unblock(u.id);
    else await adminApi.block(u.id, "bloqueado pelo admin");
    await loadUsers(q);
  }

  function openGrant(u: AdminUser) {
    setGrantModal(u);
    setGrantForm({ amount: "10", reason: "cortesia" });
  }
  async function submitGrant(e: React.FormEvent) {
    e.preventDefault();
    if (!grantModal) return;
    try {
      const amount = grantForm.amount;
      await adminApi.adjustCredits(grantModal.id, { amount, kind: Number(amount) >= 0 ? "bonus" : "manual_adjustment", reason: grantForm.reason || "ajuste admin" });
      await loadUsers(q);
      setGrantModal(null);
    } catch (e) { setErr((e as Error).message); }
  }

  async function createPromo(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createPromotion(newPromo);
      setNewPromo({ code: "", name: "", type: "refund_if_lose" });
      setPromos((await adminApi.promotions()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function createCoupon(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createCoupon({
        ...newCoupon,
        discount_value: newCoupon.discount_type === "bonus_credits" ? undefined : Number(newCoupon.discount_value),
        bonus_credits: newCoupon.discount_type === "bonus_credits" ? Number(newCoupon.discount_value) : undefined,
        min_purchase_brl: newCoupon.min_purchase_brl ? Number(newCoupon.min_purchase_brl) : undefined,
        valid_days: newCoupon.valid_days ? Number(newCoupon.valid_days) : undefined,
        description: newCoupon.description || undefined,
      });
      setNewCoupon({ promotion_id: "", code: "", discount_type: "percentage", discount_value: "10",
        min_purchase_brl: "", first_purchase_only: false, description: "", valid_days: "30" });
      setCoupons((await adminApi.coupons()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  function openEditCoupon(c: Record<string, unknown>) {
    setEditCouponModal(c);
    setEditCouponForm({
      discount_type: String(c.discount_type ?? "percentage"),
      discount_value: String(c.discount_type === "bonus_credits" ? (c.bonus_credits ?? "") : (c.discount_value ?? "")),
      min_purchase_brl: String(c.min_purchase_brl ?? ""),
      usage_limit: String(c.usage_limit ?? ""),
      per_user_limit: String(c.per_user_limit ?? ""),
      valid_to: c.valid_to ? String(c.valid_to).slice(0, 10) : "",
      first_purchase_only: Boolean(c.first_purchase_only),
      description: String(c.description ?? ""),
      active: Boolean(c.active),
    });
  }
  async function submitEditCoupon(e: React.FormEvent) {
    e.preventDefault();
    if (!editCouponModal) return;
    try {
      const f = editCouponForm;
      const patch: Record<string, unknown> = {
        discount_type: f.discount_type,
        min_purchase_brl: f.min_purchase_brl ? Number(f.min_purchase_brl) : null,
        usage_limit: f.usage_limit ? Number(f.usage_limit) : null,
        per_user_limit: f.per_user_limit ? Number(f.per_user_limit) : null,
        valid_to: f.valid_to ? new Date(`${f.valid_to}T23:59:59`).toISOString() : null,
        first_purchase_only: f.first_purchase_only,
        description: f.description,
        active: f.active,
      };
      if (f.discount_type === "bonus_credits") patch.bonus_credits = Number(f.discount_value);
      else patch.discount_value = Number(f.discount_value);
      await adminApi.patchCoupon(String(editCouponModal.id), patch);
      setCoupons((await adminApi.coupons()).items);
      setEditCouponModal(null);
    } catch (e) { setErr((e as Error).message); }
  }

  function deleteCoupon(c: Record<string, unknown>) {
    setConfirmState({
      message: `Excluir o cupom ${c.code}?`,
      onConfirm: async () => {
        try {
          await adminApi.deleteCoupon(String(c.id));
          setCoupons((await adminApi.coupons()).items);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  async function createPackage(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createPackage({
        name: newPackage.name, credits: Number(newPackage.credits),
        price_brl: Number(newPackage.price_brl), bonus_credits: Number(newPackage.bonus_credits),
      });
      setNewPackage({ name: "", credits: "10", price_brl: "10.00", bonus_credits: "0" });
      setPackages((await adminApi.packages()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function cyclePackageStatus(p: Record<string, unknown>) {
    const order = ["ativo", "oculto", "arquivado"];
    const next = order[(order.indexOf(String(p.status)) + 1) % order.length];
    try {
      await adminApi.patchPackage(String(p.id), { status: next });
      setPackages((await adminApi.packages()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function loadAffiliates(status = partnerFilter) {
    try { setAffiliates((await adminApi.affiliates(status || undefined)).items); } catch (e) { setErr((e as Error).message); }
  }

  async function loadPartnerRequests() {
    try {
      const [cr, pc] = await Promise.all([adminApi.couponRequests("pending"), adminApi.pendingCounts()]);
      setCouponRequests(cr.items); setPendingCounts(pc);
    } catch { /* silencioso — badge/aba são auxiliares */ }
  }

  async function decideCouponRequest(id: string, action: "approve" | "reject") {
    try {
      if (action === "reject") {
        const reason = window.prompt("Motivo da recusa (será enviado por e-mail ao parceiro):") || "";
        if (!reason.trim()) return;
        await adminApi.rejectCouponRequest(id, reason.trim());
      } else {
        const kind = window.prompt("Limite por 'dias' ou 'faturamento'? Digite: dias / faturamento", "dias");
        if (kind === null) return;
        if (kind.toLowerCase().startsWith("fat")) {
          const v = window.prompt("Teto de faturamento pré-desconto (R$):", "500");
          if (!v) return;
          await adminApi.approveCouponRequest(id, { limit_type: "revenue", limit_revenue_brl: v });
        } else {
          const d = window.prompt("Prazo em dias:", "30");
          if (!d) return;
          await adminApi.approveCouponRequest(id, { limit_type: "days", limit_days: Number(d) });
        }
      }
      await loadPartnerRequests();
    } catch (e) { setErr((e as Error).message); }
  }

  async function createAffiliate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createAffiliate({
        ...newAffiliate, commission_pct: Number(newAffiliate.commission_pct),
        payment_type: newAffiliate.payment_type || undefined,
        discount_pcts: newAffiliate.discount_pcts ? Number(newAffiliate.discount_pcts) : undefined,
      });
      setNewAffiliate({ name: "", code: "", commission_pct: "10", contact_email: "", contact_phone: "", cpf: "", payment_type: "", discount_pcts: "" });
      await loadAffiliates();
    } catch (e) { setErr((e as Error).message); }
  }

  async function approveAffiliate(a: Record<string, unknown>) {
    const draft = approveCodeDrafts[String(a.id)];
    const code = draft && draft.trim() && draft.trim().toUpperCase() !== String(a.code).toUpperCase() ? draft.trim() : undefined;
    try { await adminApi.approveAffiliate(String(a.id), code); await loadAffiliates(); } catch (e) { setErr((e as Error).message); }
  }

  function openReject(a: Record<string, unknown>) {
    setRejectModal(a);
    setRejectReason("");
  }
  async function submitReject(e: React.FormEvent) {
    e.preventDefault();
    if (!rejectModal) return;
    try {
      await adminApi.rejectAffiliate(String(rejectModal.id), rejectReason || undefined);
      setRejectModal(null);
      await loadAffiliates();
    } catch (e) { setErr((e as Error).message); }
  }

  async function resendInvite(a: Record<string, unknown>) {
    try {
      await adminApi.resendAffiliateInvite(String(a.id));
      const targetContact = String(a.contact_email || a.name || "");
      toast({
        title: "Convite reenviado com sucesso!",
        description: `Um novo e-mail com link de ativação válido foi enviado para ${targetContact}.`,
      });
      console.log(`[Admin] Convite de parceiro reenviado para affiliate_id=${a.id}, email=${targetContact}`);
      await loadAffiliates();
    } catch (e) {
      const errMsg = (e as Error).message || "Erro ao reenviar convite.";
      setErr(errMsg);
      toast({
        variant: "destructive",
        title: "Erro ao reenviar convite",
        description: errMsg,
      });
      console.error(`[Admin] Erro ao reenviar convite para affiliate_id=${a.id}:`, e);
    }
  }

  async function resetTestAccount(e: React.FormEvent) {
    e.preventDefault();
    if (!testPassword || testPassword.length < 6) {
      toast({
        variant: "destructive",
        title: "Senha inválida",
        description: "A senha deve ter no mínimo 6 caracteres.",
      });
      return;
    }
    setTestAccountBusy(true);
    setTestAccountMsg(null);
    try {
      const res = await adminApi.resetTestAccountPassword(testPassword);
      setTestAccountMsg(res.message);
      setTestPassword("");
      toast({
        title: "Senha da Conta de Teste Resetada!",
        description: res.message,
      });
      console.log("[Admin] Reset da conta de teste realizado:", res);
    } catch (err) {
      const errMsg = (err as Error).message || "Falha ao resetar a senha da conta de teste.";
      setErr(errMsg);
      toast({
        variant: "destructive",
        title: "Erro ao resetar conta de teste",
        description: errMsg,
      });
      console.error("[Admin] Erro no reset da conta de teste:", err);
    } finally {
      setTestAccountBusy(false);
    }
  }


  async function toggleDemoAccess(a: Record<string, unknown>) {
    try { await adminApi.setAffiliateDemoAccess(String(a.id), !a.demo_access_enabled); await loadAffiliates(); } catch (e) { setErr((e as Error).message); }
  }

  function deleteAffiliate(a: Record<string, unknown>) {
    setConfirmState({
      message: `Excluir o parceiro ${a.name}? Isso remove atribuições, comissões, pagamentos e logs de acesso à conta demo. Não pode ser desfeito.`,
      onConfirm: async () => {
        try {
          await adminApi.deleteAffiliate(String(a.id));
          await loadAffiliates();
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  async function createBanner(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createBanner({
        title: newBanner.title, body: newBanner.body, image_url: newBanner.image_url || undefined,
        priority: Number(newBanner.priority), sort_order: Number(newBanner.sort_order),
      });
      setNewBanner({ title: "", body: "", image_url: "", priority: "0", sort_order: "0" });
      setBanners((await adminApi.banners()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function toggleBanner(b: Record<string, unknown>) {
    try {
      await adminApi.patchBanner(String(b.id), { active: !(b.active as boolean) });
      setBanners((await adminApi.banners()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  function openEditBanner(b: Record<string, unknown>) {
    setEditBannerModal(b);
    setEditBannerForm({ title: String(b.title ?? ""), body: String(b.body ?? ""), image_url: String(b.image_url ?? "") });
  }
  async function submitEditBanner(e: React.FormEvent) {
    e.preventDefault();
    if (!editBannerModal) return;
    try {
      await adminApi.patchBanner(String(editBannerModal.id), editBannerForm);
      setBanners((await adminApi.banners()).items);
      setEditBannerModal(null);
    } catch (e) { setErr((e as Error).message); }
  }

  async function openEditLegal(d: LegalDoc) {
    setEditLegalModal(d);
    setEditLegalForm({ title: d.title, body_md: "" });
    setEditLegalLoading(true);
    try {
      const full = await legalApi.document(d.type);
      setEditLegalForm({ title: full.title, body_md: full.body_md });
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setEditLegalLoading(false);
    }
  }
  function submitEditLegal(e: React.FormEvent) {
    e.preventDefault();
    if (!editLegalModal) return;
    setConfirmState({
      message: `Publicar uma nova versão de "${editLegalModal.title}"? Isso REVOGA o aceite de todos os usuários — na próxima vez que logarem, será pedido que revisem e assinem novamente.`,
      onConfirm: async () => {
        if (!editLegalModal) return;
        try {
          await adminApi.publishLegal({ type: editLegalModal.type, title: editLegalForm.title, body_md: editLegalForm.body_md });
          setLegalDocs(await legalApi.documents());
          setEditLegalModal(null);
          setLegalMsg(`Nova versão de "${editLegalForm.title}" publicada — todos os usuários precisarão assinar novamente.`);
          setTimeout(() => setLegalMsg(null), 6000);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  function deleteBanner(b: Record<string, unknown>) {
    setConfirmState({
      message: `Excluir o banner "${b.title}"?`,
      onConfirm: async () => {
        try {
          await adminApi.deleteBanner(String(b.id));
          setBanners((await adminApi.banners()).items);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  async function createCampaign(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createCampaign({ name: newCampaign.name, priority: Number(newCampaign.priority) });
      setNewCampaign({ name: "", priority: "0" });
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function toggleCampaign(c: Record<string, unknown>) {
    try {
      await adminApi.patchCampaign(String(c.id), { active: !(c.active as boolean) });
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  function deleteCampaign(c: Record<string, unknown>) {
    setConfirmState({
      message: `Excluir a campanha "${c.name}"?`,
      onConfirm: async () => {
        try {
          await adminApi.deleteCampaign(String(c.id));
          setCampaigns((await adminApi.campaigns()).items);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  async function pickCampaignBanner(campaignId: string, bannerId: string | null) {
    try {
      await adminApi.patchCampaign(campaignId, { banner_id: bannerId });
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }
  async function toggleCampaignPackage(campaignId: string, packageId: string, has: boolean) {
    try {
      if (has) await adminApi.removeCampaignPackage(campaignId, packageId);
      else await adminApi.addCampaignPackage(campaignId, packageId);
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }
  async function toggleCampaignCoupon(campaignId: string, couponId: string, has: boolean) {
    try {
      if (has) await adminApi.removeCampaignCoupon(campaignId, couponId);
      else await adminApi.addCampaignCoupon(campaignId, couponId);
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }
  async function toggleCampaignAffiliate(campaignId: string, affiliateId: string, has: boolean) {
    try {
      if (has) await adminApi.removeCampaignAffiliate(campaignId, affiliateId);
      else await adminApi.addCampaignAffiliate(campaignId, affiliateId);
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function openCampaignDashboard(c: Record<string, unknown>) {
    try {
      const d = await adminApi.campaignDashboard(String(c.id));
      setCampaignDashModal({ name: c.name, ...d });
    } catch (e) { setErr((e as Error).message); }
  }

  function openAffPayment(a: Record<string, unknown>) {
    setAffPaymentModal(a);
    setAffPaymentForm({ amount_brl: String(a.commission_due_brl ?? "0"), method: "pix" });
  }
  async function submitAffPayment(e: React.FormEvent) {
    e.preventDefault();
    if (!affPaymentModal) return;
    try {
      await adminApi.createAffiliatePayment(String(affPaymentModal.id), {
        amount_brl: Number(affPaymentForm.amount_brl), method: affPaymentForm.method,
      });
      setAffiliates((await adminApi.affiliates()).items);
      setAffPaymentModal(null);
    } catch (e) { setErr((e as Error).message); }
  }

  async function openAffPaymentsList(a: Record<string, unknown>) {
    try {
      const res = await adminApi.affiliatePayments(String(a.id));
      setAffPaymentsListModal({ affiliate: a, items: res.items });
    } catch (e) { setErr((e as Error).message); }
  }

  async function saveAttributionDays(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.setSetting("affiliate_attribution_days", { value: { days: Number(attributionDays) } });
      setSettings((await adminApi.settings()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function saveSetting(e: React.FormEvent) {
    e.preventDefault();
    try {
      let value: unknown;
      try { value = JSON.parse(newSetting.value); } catch { value = { value: newSetting.value }; }
      await adminApi.setSetting(newSetting.key, { value: value as Record<string, unknown> });
      setNewSetting({ key: "", value: "" });
      setSettings((await adminApi.settings()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function submitDeepAnalysis(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.upsertDeepAnalysis({
        fixture_id: Number(newDeepAnalysis.fixture_id),
        analyst_name: newDeepAnalysis.analyst_name,
        markdown_content: newDeepAnalysis.markdown_content,
      });
      setNewDeepAnalysis({ fixture_id: "", analyst_name: "", markdown_content: "" });
      setDeepAnalyses((await adminApi.deepAnalyses()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  function deleteDeepAnalysis(fixtureId: number) {
    setConfirmState({
      message: "Excluir esta análise aprofundada?",
      onConfirm: async () => {
        try {
          await adminApi.deleteDeepAnalysis(fixtureId);
          setDeepAnalyses((await adminApi.deepAnalyses()).items);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  async function addFeaturedMatch(fx: PickerFixture) {
    try {
      await adminApi.createFeaturedMatch({ fixture_id: Number(fx.fixture_id), scope: fx.scope ?? "selecao" });
      setFeaturedMatches((await adminApi.featuredMatches()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function moveFeaturedMatch(index: number, dir: -1 | 1) {
    const other = index + dir;
    if (other < 0 || other >= featuredMatches.length) return;
    const a = featuredMatches[index], b = featuredMatches[other];
    try {
      await Promise.all([
        adminApi.patchFeaturedMatch(a.id, b.sort_order),
        adminApi.patchFeaturedMatch(b.id, a.sort_order),
      ]);
      setFeaturedMatches((await adminApi.featuredMatches()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  function deleteFeaturedMatch(id: string) {
    setConfirmState({
      message: "Remover esta partida dos destaques?",
      onConfirm: async () => {
        try {
          await adminApi.deleteFeaturedMatch(id);
          setFeaturedMatches((await adminApi.featuredMatches()).items);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  async function addSharedAnalysis(fx: PickerFixture) {
    try {
      await adminApi.createSharedAnalysis({
        fixture_id: Number(fx.fixture_id), home_team: fx.home, away_team: fx.away,
        scope: fx.scope ?? "selecao", tournament: fx.tournament ?? "Amistoso", neutral: fx.neutral ?? false,
        match_date: fx.date, league_name: fx.league_name,
      });
      setSharedAnalyses((await adminApi.sharedAnalyses()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  function deleteSharedAnalysis(id: string) {
    setConfirmState({
      message: "Excluir este link compartilhado?",
      onConfirm: async () => {
        try {
          await adminApi.deleteSharedAnalysis(id);
          setSharedAnalyses((await adminApi.sharedAnalyses()).items);
        } catch (e) { setErr((e as Error).message); }
      },
    });
  }

  function shareUrl(token: string): string {
    const origin = typeof window !== "undefined" ? window.location.origin : "";
    return `${origin}/compartilhado/${token}`;
  }

  async function copyShareUrl(url: string) {
    try { await navigator.clipboard.writeText(url); } catch { /* ignora */ }
  }

  if (loading || !isAdmin) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  const rev = dashboard?.revenue as Record<string, string> | undefined;
  const users_ = dashboard?.users as Record<string, number> | undefined;
  const credits_ = dashboard?.credits as Record<string, string> | undefined;
  const byPartner = (dashboard?.by_partner as Record<string, unknown>[] | undefined) ?? [];
  const pickerCampaign = pickerModal ? campaigns.find((c) => String(c.id) === pickerModal.campaignId) : null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><Shield className="w-6 h-6 text-primary" /> Painel administrativo</h1>
      {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      <Tabs defaultValue={isOwner ? "dashboard" : "promocoes"}>
        <TabsList className="flex flex-wrap h-auto w-full gap-1">
          {isOwner && (
            <>
              <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
              <TabsTrigger value="usuarios">Usuários</TabsTrigger>
              <TabsTrigger value="financeiro">Financeiro</TabsTrigger>
            </>
          )}
          <TabsTrigger value="promocoes">Promoções</TabsTrigger>
          {isOwner && (
            <>
              <TabsTrigger value="afiliados" className="relative">
                Parceiros
                {pendingCounts && pendingCounts.total > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold leading-none"
                    title={`${pendingCounts.partner_applications} solicitações de parceria, ${pendingCounts.coupon_requests} de cupom`}>
                    {pendingCounts.total}
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="documentos">Documentos</TabsTrigger>
              <TabsTrigger value="config">Configurações</TabsTrigger>
            </>
          )}
          <TabsTrigger value="deep">Análise Aprofundada</TabsTrigger>
          <TabsTrigger value="destaque">Partidas em Destaque</TabsTrigger>
          <TabsTrigger value="compartilhar">Compartilhar Análise</TabsTrigger>
          {isOwner && <TabsTrigger value="auditoria">Auditoria</TabsTrigger>}
        </TabsList>

        {/* ---------------- Dashboard ---------------- */}
        {isOwner && (
          <TabsContent value="dashboard">
            <Card>
              <CardContent className="space-y-4 pt-6">
                <RevenueChart rev={rev} />
                <PartnerRevenueChart items={byPartner} />
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Ticket médio</div><div className="text-xl font-bold">R$ {Number(rev?.ticket_medio_brl ?? 0).toFixed(2)}</div></div>
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Créditos vendidos</div><div className="text-xl font-bold">{Math.round(Number(credits_?.vendidos ?? 0))}</div></div>
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Créditos promo</div><div className="text-xl font-bold">{Math.round(Number(credits_?.promocionais ?? 0))}</div></div>
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Usuários ativos (30d)</div><div className="text-xl font-bold">{users_?.active_30d ?? 0}</div></div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Usuários pagantes</div><div className="text-xl font-bold">{users_?.paying_total ?? 0}</div></div>
                </div>
                {Array.isArray(dashboard?.by_package) && (dashboard!.by_package as Record<string, unknown>[]).length > 0 && (
                  <div>
                    <div className="text-sm font-medium mb-2">Receita por pacote</div>
                    <div className="divide-y text-sm">
                      {(dashboard!.by_package as { name: string; orders: number; revenue_brl: string }[]).map((p) => (
                        <div key={p.name} className="flex justify-between py-1.5">
                          <span>{p.name} ({p.orders} pedidos)</span><span className="font-mono">R$ {p.revenue_brl}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {/* ---------------- Usuários ---------------- */}
        {isOwner && (
          <TabsContent value="usuarios">
            <Card>
              <CardHeader><CardTitle className="text-lg">Usuários ({users.length})</CardTitle></CardHeader>
              <CardContent>
                <div className="flex gap-2 mb-4">
                  <Input placeholder="Buscar por nome/e-mail/CPF..." value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && loadUsers(q)} />
                  <Button variant="outline" onClick={() => loadUsers(q)}>Buscar</Button>
                </div>
                <div className="divide-y text-sm">
                  {users.map((u) => (
                    <div key={u.id} className="flex items-center justify-between py-2.5 gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="font-medium truncate">{u.full_name} {u.role !== "user" && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">{u.role}</span>}</div>
                        <div className="text-xs text-muted-foreground truncate">{u.email} · {u.status} · {u.available_balance ?? "0"} créditos</div>
                      </div>
                      <div className="flex gap-2 shrink-0 items-center">
                        {u.email !== "valerioeducfin@gmail.com" ? (
                          <select
                            className="border rounded px-2 py-1 text-xs bg-background focus:ring-1 focus:ring-primary outline-none"
                            value={u.role || "user"}
                            onChange={async (e) => {
                              try {
                                await adminApi.updateUserRole(u.id, e.target.value);
                                await loadUsers(q);
                              } catch (err) {
                                setErr((err as Error).message);
                              }
                            }}
                          >
                            <option value="user">Usuário</option>
                            <option value="partner">Parceiro</option>
                            <option value="manager">Gestor</option>
                            <option value="owner">Proprietário</option>
                          </select>
                        ) : (
                          <span className="text-xs text-muted-foreground font-semibold px-2">Proprietário Raiz</span>
                        )}
                        <Button size="sm" variant="outline" onClick={() => openGrant(u)}><Coins className="w-3.5 h-3.5" /></Button>
                        <Button size="sm" variant={u.status === "blocked" ? "outline" : "destructive"} onClick={() => toggleBlock(u)}>
                          {u.status === "blocked" ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Ban className="w-3.5 h-3.5" />}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {/* ---------------- Financeiro ---------------- */}
        {isOwner && (
          <TabsContent value="financeiro">
            <Card>
              <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <CardTitle className="text-lg">Financeiro & Pagamentos ({payments.length})</CardTitle>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    placeholder="Filtrar por usuário ou e-mail..."
                    className="w-48 h-8 text-xs"
                    value={payUserSearch}
                    onChange={(e) => setPayUserSearch(e.target.value)}
                  />
                  <div className="flex items-center gap-1 text-xs">
                    <span>De:</span>
                    <Input
                      type="date"
                      className="w-32 h-8 text-xs"
                      value={payDateFrom}
                      onChange={(e) => setPayDateFrom(e.target.value)}
                    />
                  </div>
                  <div className="flex items-center gap-1 text-xs">
                    <span>Até:</span>
                    <Input
                      type="date"
                      className="w-32 h-8 text-xs"
                      value={payDateTo}
                      onChange={(e) => setPayDateTo(e.target.value)}
                    />
                  </div>
                  <Button
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => {
                      adminApi.payments(50, payUserSearch, payDateFrom, payDateTo).then((r) => setPayments(r.items)).catch(() => {});
                    }}
                  >
                    Filtrar
                  </Button>
                  {(payUserSearch || payDateFrom || payDateTo) && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 text-xs"
                      onClick={() => {
                        setPayUserSearch(""); setPayDateFrom(""); setPayDateTo("");
                        adminApi.payments(50, "", "", "").then((r) => setPayments(r.items)).catch(() => {});
                      }}
                    >
                      Limpar
                    </Button>
                  )}
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs text-muted-foreground">
                      <tr>
                        <th className="text-left px-3 py-2 font-medium">Data</th>
                        <th className="text-left px-3 py-2 font-medium">Comprador</th>
                        <th className="text-left px-3 py-2 font-medium">E-mail</th>
                        <th className="text-right px-3 py-2 font-medium">Créditos</th>
                        <th className="text-right px-3 py-2 font-medium">Valor (R$)</th>
                        <th className="text-center px-3 py-2 font-medium">Status</th>
                        <th className="text-left px-3 py-2 font-medium">Motivo / Detalhes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {payments.map((p) => {
                        const stLabel = String(p.status_label || p.status || "—");
                        const stReason = String(p.status_reason || "Status informado pelo gateway");
                        const isSuccess = p.status === "paid" || p.status === "completed" || p.status === "approved";
                        const isPending = p.status === "pending";

                        return (
                          <tr key={String(p.id)} className="hover:bg-muted/30 text-xs">
                            <td className="px-3 py-2 text-muted-foreground whitespace-nowrap">{fmt(String(p.created_at))}</td>
                            <td className="px-3 py-2 font-medium">{String(p.user_name || "Usuário")}</td>
                            <td className="px-3 py-2 text-muted-foreground">{String(p.user_email || "—")}</td>
                            <td className="px-3 py-2 text-right font-mono font-semibold">{String(p.credits)}</td>
                            <td className="px-3 py-2 text-right font-mono font-semibold text-emerald-600">
                              R$ {Number(p.amount_brl || 0).toFixed(2)}
                            </td>
                            <td className="px-3 py-2 text-center">
                              <span
                                className={`inline-block px-2 py-0.5 rounded text-[10px] font-semibold ${
                                  isSuccess
                                    ? "bg-emerald-500/10 text-emerald-600"
                                    : isPending
                                    ? "bg-amber-500/10 text-amber-600"
                                    : "bg-red-500/10 text-red-600"
                                }`}
                              >
                                {stLabel}
                              </span>
                            </td>
                            <td className="px-3 py-2 text-muted-foreground max-w-xs truncate" title={stReason}>
                              {stReason}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {payments.length === 0 && <p className="text-sm text-muted-foreground p-4 text-center">Nenhum registro de pagamento encontrado.</p>}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {/* ---------------- Promoções (unificada: Promoções + Cupons + Pacotes + Banners + Campanhas) ---------------- */}
        <TabsContent value="promocoes">
          <div className="flex gap-1.5 flex-wrap mb-4">
            {([
              { key: "promocoes", label: "Promoções" },
              isOwner && { key: "cupons", label: "Cupons" },
              isOwner && { key: "pacotes", label: "Pacotes" },
              isOwner && { key: "banners", label: "Banners" },
              isOwner && { key: "campanhas", label: "Campanhas" },
            ].filter(Boolean) as { key: "promocoes" | "cupons" | "pacotes" | "banners" | "campanhas"; label: string }[]).map((s) => (
              <Button key={s.key} size="sm" variant={promoSection === s.key ? "default" : "outline"} onClick={() => setPromoSection(s.key)}>
                {s.label}
              </Button>
            ))}
          </div>

          {promoSection === "promocoes" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">Promoções</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={createPromo} className="flex flex-wrap gap-2 items-end">
                <Field label="Código"><Input className="w-32" value={newPromo.code} onChange={(e) => setNewPromo({ ...newPromo, code: e.target.value })} required /></Field>
                <Field label="Nome" className="flex-1 min-w-40"><Input value={newPromo.name} onChange={(e) => setNewPromo({ ...newPromo, name: e.target.value })} required /></Field>
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {promos.map((p) => (
                  <div key={String(p.id)} className="flex items-center justify-between py-2">
                    <span>{String(p.name)} <span className="text-xs text-muted-foreground">({String(p.code)} · {String(p.type)})</span></span>
                    <Button size="sm" variant="outline" onClick={async () => { await adminApi.patchPromotion(String(p.id), { active: !(p.active as boolean) }); setPromos((await adminApi.promotions()).items); }}>
                      {(p.active as boolean) ? "Desativar" : "Ativar"}
                    </Button>
                  </div>
                ))}
                {promos.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma promoção.</p>}
              </div>
            </CardContent>
          </Card>
          )}

          {isOwner && promoSection === "cupons" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">Cupons</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">Todo cupom precisa de uma promoção existente (crie na aba Promoções primeiro e cole o ID abaixo).</p>
              <form onSubmit={createCoupon} className="flex flex-wrap gap-2 items-end">
                <Field label="ID da promoção"><Input className="w-56" value={newCoupon.promotion_id} onChange={(e) => setNewCoupon({ ...newCoupon, promotion_id: e.target.value })} required /></Field>
                <Field label="Código"><Input className="w-28" value={newCoupon.code} onChange={(e) => setNewCoupon({ ...newCoupon, code: e.target.value })} required /></Field>
                <Field label="Tipo de desconto">
                  <select className="border rounded-md px-2 py-2 text-sm bg-background" value={newCoupon.discount_type} onChange={(e) => setNewCoupon({ ...newCoupon, discount_type: e.target.value })}>
                    <option value="percentage">% desconto</option>
                    <option value="fixed">R$ desconto</option>
                    <option value="bonus_credits">créditos bônus</option>
                  </select>
                </Field>
                <Field label="Valor"><Input className="w-24" type="number" value={newCoupon.discount_value} onChange={(e) => setNewCoupon({ ...newCoupon, discount_value: e.target.value })} required /></Field>
                <Field label="Compra mín. (R$)"><Input className="w-32" type="number" value={newCoupon.min_purchase_brl} onChange={(e) => setNewCoupon({ ...newCoupon, min_purchase_brl: e.target.value })} /></Field>
                <Field label="Duração (dias)"><Input className="w-28" type="number" min="1" value={newCoupon.valid_days} onChange={(e) => setNewCoupon({ ...newCoupon, valid_days: e.target.value })} /></Field>
                <label className="flex items-center gap-1.5 text-xs pb-2">
                  <input type="checkbox" checked={newCoupon.first_purchase_only} onChange={(e) => setNewCoupon({ ...newCoupon, first_purchase_only: e.target.checked })} />
                  só 1ª compra
                </label>
                <Field label="Regras/descrição" className="flex-1 min-w-48"><Input value={newCoupon.description} onChange={(e) => setNewCoupon({ ...newCoupon, description: e.target.value })} /></Field>
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {coupons.map((c) => (
                  <div key={String(c.id)} className="flex items-center justify-between py-2 gap-2">
                    <div className="min-w-0">
                      <div>{String(c.code)} <span className="text-xs text-muted-foreground">({String(c.discount_type)} · {c.redemptions as number} usos{(c.first_purchase_only as boolean) ? " · 1ª compra" : ""})</span></div>
                      {!!c.description && <div className="text-xs text-muted-foreground truncate">{String(c.description)}</div>}
                    </div>
                    <div className="flex gap-1.5 shrink-0">
                      <Button size="sm" variant="outline" onClick={() => openEditCoupon(c)}>Editar</Button>
                      <Button size="sm" variant="outline" onClick={async () => { await adminApi.patchCoupon(String(c.id), { active: !(c.active as boolean) }); setCoupons((await adminApi.coupons()).items); }}>
                        {(c.active as boolean) ? "Desativar" : "Ativar"}
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => deleteCoupon(c)}>Excluir</Button>
                    </div>
                  </div>
                ))}
                {coupons.length === 0 && <p className="text-sm text-muted-foreground">Nenhum cupom.</p>}
              </div>

              <div>
                <div className="text-sm font-medium mb-2 mt-4">Análise por Cupom</div>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs text-muted-foreground">
                      <tr>
                        <th className="text-left font-medium px-3 py-2">Código</th>
                        <th className="text-right font-medium px-3 py-2">Receita</th>
                        <th className="text-right font-medium px-3 py-2">Desconto</th>
                        <th className="text-right font-medium px-3 py-2">Ticket médio</th>
                        <th className="text-right font-medium px-3 py-2">Pedidos</th>
                        <th className="text-right font-medium px-3 py-2">ROI</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {couponAnalytics.map((a) => (
                        <tr key={String(a.coupon_id)} className="hover:bg-muted/30">
                          <td className="px-3 py-2 font-medium">{String(a.code)}</td>
                          <td className="px-3 py-2 text-right font-mono">R$ {String(a.revenue_brl)}</td>
                          <td className="px-3 py-2 text-right font-mono">R$ {String(a.discount_given_brl)}</td>
                          <td className="px-3 py-2 text-right font-mono">R$ {String(a.ticket_medio_brl)}</td>
                          <td className="px-3 py-2 text-right">{a.orders_paid as number}</td>
                          <td className="px-3 py-2 text-right">{a.roi != null ? Number(a.roi).toFixed(2) : "n/d"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {couponAnalytics.length === 0 && <p className="text-sm text-muted-foreground p-3">Sem dados ainda.</p>}
                </div>
              </div>
            </CardContent>
          </Card>
          )}

          {isOwner && promoSection === "pacotes" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">Pacotes de crédito</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">Pacotes nunca são excluídos fisicamente (pedidos antigos dependem deles) — use o status ativo/oculto/arquivado.</p>
              <form onSubmit={createPackage} className="flex flex-wrap gap-2 items-end">
                <Field label="Nome" className="flex-1 min-w-40"><Input value={newPackage.name} onChange={(e) => setNewPackage({ ...newPackage, name: e.target.value })} required /></Field>
                <Field label="Créditos"><Input className="w-24" type="number" value={newPackage.credits} onChange={(e) => setNewPackage({ ...newPackage, credits: e.target.value })} required /></Field>
                <Field label="Preço (R$)"><Input className="w-28" type="number" step="0.01" value={newPackage.price_brl} onChange={(e) => setNewPackage({ ...newPackage, price_brl: e.target.value })} required /></Field>
                <Field label="Bônus"><Input className="w-24" type="number" value={newPackage.bonus_credits} onChange={(e) => setNewPackage({ ...newPackage, bonus_credits: e.target.value })} /></Field>
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {packages.map((p) => (
                  <div key={String(p.id)} className="flex items-center justify-between py-2 gap-2 flex-wrap">
                    <span>{String(p.name)} <span className="text-xs text-muted-foreground">R$ {String(p.price_brl)} · {p.featured_badge ? String(p.featured_badge) : "sem selo"} · {String(p.status)}</span></span>
                    <div className="flex gap-1.5">
                      {["mais_vendido", "melhor_oferta", "oferta_limitada", "melhor_para_comecar", "melhor_custo_beneficio"].map((b) => (
                        <Button key={b} size="sm" variant={p.featured_badge === b ? "default" : "outline"} title={b}
                               onClick={async () => { await adminApi.patchPackage(String(p.id), { featured_badge: p.featured_badge === b ? null : b }); setPackages((await adminApi.packages()).items); }}>
                          {b === "mais_vendido" ? "★" : b === "melhor_oferta" ? "$" : b === "oferta_limitada" ? "⏱" : b === "melhor_para_comecar" ? "🌱" : "💎"}
                        </Button>
                      ))}
                      <Button size="sm" variant="outline" onClick={() => cyclePackageStatus(p)}>{String(p.status)}</Button>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          )}

          {isOwner && promoSection === "banners" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">Banners promocionais</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={createBanner} className="flex flex-wrap gap-2 items-end">
                <Field label="Título"><Input className="w-56" value={newBanner.title} onChange={(e) => setNewBanner({ ...newBanner, title: e.target.value })} required /></Field>
                <Field label="Texto" className="flex-1 min-w-40"><Input value={newBanner.body} onChange={(e) => setNewBanner({ ...newBanner, body: e.target.value })} /></Field>
                <Field label="Imagem de fundo (URL)" className="flex-1 min-w-56"><Input value={newBanner.image_url} onChange={(e) => setNewBanner({ ...newBanner, image_url: e.target.value })} placeholder="https://..." /></Field>
                <Field label="Prioridade"><Input className="w-24" type="number" value={newBanner.priority} onChange={(e) => setNewBanner({ ...newBanner, priority: e.target.value })} /></Field>
                <Field label="Ordem"><Input className="w-24" type="number" value={newBanner.sort_order} onChange={(e) => setNewBanner({ ...newBanner, sort_order: e.target.value })} /></Field>
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="space-y-3">
                {banners.map((b) => (
                  <div key={String(b.id)} className="relative overflow-hidden rounded-lg border">
                    {!!b.image_url && (
                      <div className="absolute inset-0">
                        <img src={String(b.image_url)} alt="" className="w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/85 to-background/50" />
                      </div>
                    )}
                    <div className="relative flex items-center justify-between py-2.5 px-3 gap-2 flex-wrap">
                      <div className="min-w-0">
                        <div className="font-medium">{String(b.title)} <span className="text-xs text-muted-foreground">(prioridade {String(b.priority)} · ordem {String(b.sort_order)} · {(b.active as boolean) ? "ativo" : "inativo"})</span></div>
                        {!!b.body && <div className="text-xs text-muted-foreground">{String(b.body)}</div>}
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button size="sm" variant="outline" onClick={() => openEditBanner(b)}>Editar</Button>
                        <Button size="sm" variant="outline" onClick={() => toggleBanner(b)}>{(b.active as boolean) ? "Desativar" : "Ativar"}</Button>
                        <Button size="sm" variant="destructive" onClick={() => deleteBanner(b)}>Excluir</Button>
                      </div>
                    </div>
                  </div>
                ))}
                {banners.length === 0 && <p className="text-sm text-muted-foreground">Nenhum banner.</p>}
              </div>
            </CardContent>
          </Card>
          )}

          {isOwner && promoSection === "campanhas" && (
          <Card>
            <CardHeader><CardTitle className="text-lg">Campanhas</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">Uma campanha amarra banner + cupons + pacotes + afiliados + período + prioridade.</p>
              <form onSubmit={createCampaign} className="flex flex-wrap gap-2 items-end">
                <Field label="Nome" className="flex-1 min-w-40"><Input value={newCampaign.name} onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })} required /></Field>
                <Field label="Prioridade"><Input className="w-24" type="number" value={newCampaign.priority} onChange={(e) => setNewCampaign({ ...newCampaign, priority: e.target.value })} /></Field>
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {campaigns.map((c) => (
                  <div key={String(c.id)} className="py-3 space-y-1.5">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="font-medium">{String(c.name)} <span className="text-xs text-muted-foreground">(prioridade {String(c.priority)} · {(c.active as boolean) ? "ativa" : "inativa"})</span></span>
                      <div className="flex gap-1.5 shrink-0">
                        <Button size="sm" variant="outline" onClick={() => openCampaignDashboard(c)}>Dashboard</Button>
                        <Button size="sm" variant="outline" onClick={() => toggleCampaign(c)}>{(c.active as boolean) ? "Desativar" : "Ativar"}</Button>
                        <Button size="sm" variant="destructive" onClick={() => deleteCampaign(c)}>Excluir</Button>
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      banner: {banners.find((b) => String(b.id) === c.banner_id)?.title as string ?? "nenhum"} · pacotes: {(c.package_ids as string[]).length} · cupons: {(c.coupon_ids as string[]).length} · afiliados: {(c.affiliate_ids as string[]).length}
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      <Button size="sm" variant="outline" onClick={() => setPickerModal({ campaignId: String(c.id), kind: "banner" })}>+ banner</Button>
                      <Button size="sm" variant="outline" onClick={() => setPickerModal({ campaignId: String(c.id), kind: "package" })}>+ pacote</Button>
                      <Button size="sm" variant="outline" onClick={() => setPickerModal({ campaignId: String(c.id), kind: "coupon" })}>+ cupom</Button>
                      <Button size="sm" variant="outline" onClick={() => setPickerModal({ campaignId: String(c.id), kind: "affiliate" })}>+ afiliado</Button>
                    </div>
                  </div>
                ))}
                {campaigns.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma campanha.</p>}
              </div>
            </CardContent>
          </Card>
          )}
        </TabsContent>

        {/* ---------------- Parceiros (afiliados) ---------------- */}
        {isOwner && (
          <TabsContent value="afiliados" className="space-y-4">
            {couponRequests.length > 0 && (
              <Card className="border-amber-500/40">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    Solicitações de cupom promocional
                    <span className="min-w-[18px] h-[18px] px-1 flex items-center justify-center rounded-full bg-amber-500 text-white text-[10px] font-bold">{couponRequests.length}</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {couponRequests.map((r) => (
                    <div key={String(r.id)} className="flex flex-wrap items-center justify-between gap-2 text-sm border rounded-md px-3 py-2">
                      <div>
                        <span className="font-semibold">{String(r.affiliate_name)}</span>
                        <span className="text-muted-foreground"> ({String(r.affiliate_code)})</span>
                        {" · "}
                        <span className="font-mono uppercase font-semibold">{String(r.requested_code)}</span>
                        <span className="text-muted-foreground"> · {Number(r.discount_pct)}% desconto / {30 - Number(r.discount_pct)}% comissão</span>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => decideCouponRequest(String(r.id), "approve")}>Aprovar</Button>
                        <Button size="sm" variant="outline" onClick={() => decideCouponRequest(String(r.id), "reject")}>Recusar</Button>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
            <Card>
              <CardHeader><CardTitle className="text-lg">Parceiros</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <form onSubmit={createAffiliate} className="flex flex-wrap gap-2 items-end">
                  <Field label="Nome" className="flex-1 min-w-40"><Input value={newAffiliate.name} onChange={(e) => setNewAffiliate({ ...newAffiliate, name: e.target.value })} required /></Field>
                  <Field label="Código (link)"><Input className="w-32" value={newAffiliate.code} onChange={(e) => setNewAffiliate({ ...newAffiliate, code: e.target.value })} required /></Field>
                  <Field label="Comissão (%)"><Input className="w-24" type="number" value={newAffiliate.commission_pct} onChange={(e) => setNewAffiliate({ ...newAffiliate, commission_pct: e.target.value })} /></Field>
                  <Field label="CPF"><Input className="w-32" value={newAffiliate.cpf} onChange={(e) => setNewAffiliate({ ...newAffiliate, cpf: e.target.value })} /></Field>
                  <Field label="E-mail de contato"><Input className="w-52" type="email" value={newAffiliate.contact_email} onChange={(e) => setNewAffiliate({ ...newAffiliate, contact_email: e.target.value })} /></Field>
                  <Field label="Telefone de contato"><Input className="w-40" value={newAffiliate.contact_phone} onChange={(e) => setNewAffiliate({ ...newAffiliate, contact_phone: e.target.value })} /></Field>
                  <Field label="Forma de pagamento">
                    <select className="border rounded-md px-2 py-2 text-sm bg-background w-28" value={newAffiliate.payment_type} onChange={(e) => setNewAffiliate({ ...newAffiliate, payment_type: e.target.value })}>
                      <option value="">—</option>
                      <option value="pf">PF</option>
                      <option value="pj">PJ</option>
                    </select>
                  </Field>
                  <Field label="Desconto do cupom (%)">
                    <select className="border rounded-md px-2 py-2 text-sm bg-background w-28" value={newAffiliate.discount_pcts} onChange={(e) => setNewAffiliate({ ...newAffiliate, discount_pcts: e.target.value })}>
                      <option value="">—</option>
                      {[5, 10, 15, 20, 25].map((d) => <option key={d} value={d}>{d}%</option>)}
                    </select>
                  </Field>
                  <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar (já aprovado)</Button>
                </form>
                <p className="text-xs text-muted-foreground">
                  Preenchendo CPF + e-mail + telefone, o convite para definir senha é enviado automaticamente.
                  Solicitações públicas (via /parceiro/solicitar) aparecem abaixo como &quot;pendente&quot;.
                </p>

                {/* Filtros de Busca e Ordenação de Receita */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex gap-1.5 flex-wrap">
                    {[
                      { key: "", label: "Todos" },
                      { key: "pending", label: "Pendentes" },
                      { key: "active", label: "Ativos" },
                      { key: "paused", label: "Pausados" },
                      { key: "rejected", label: "Rejeitados" },
                    ].map((f) => (
                      <Button
                        key={f.key}
                        size="sm"
                        variant={partnerFilter === f.key ? "default" : "outline"}
                        onClick={() => { setPartnerFilter(f.key); loadAffiliates(f.key); }}
                      >
                        {f.label}
                      </Button>
                    ))}
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <Input
                      placeholder="Pesquisar por nome ou e-mail..."
                      className="w-56 h-8 text-xs"
                      value={partnerSearch}
                      onChange={(e) => setPartnerSearch(e.target.value)}
                    />
                    <select
                      className="border rounded-md px-2 py-1.5 text-xs bg-background h-8"
                      value={partnerSortRevenue}
                      onChange={(e) => setPartnerSortRevenue(e.target.value as "none" | "desc" | "asc")}
                    >
                      <option value="none">Ordenação: Nome (A-Z)</option>
                      <option value="desc">Receita Gerada (Maior → Menor)</option>
                      <option value="asc">Receita Gerada (Menor → Maior)</option>
                    </select>
                  </div>
                </div>

                {/* Cards Quadrados (4 por linha) */}
                {(() => {
                  let list = [...affiliates];

                  // Filtro por pesquisa (nome ou e-mail)
                  if (partnerSearch.trim()) {
                    const q = partnerSearch.trim().toLowerCase();
                    list = list.filter((a) =>
                      String(a.name || "").toLowerCase().includes(q) ||
                      String(a.contact_email || "").toLowerCase().includes(q) ||
                      String(a.code || "").toLowerCase().includes(q)
                    );
                  }

                  // Ordenação
                  if (partnerSortRevenue === "desc") {
                    list.sort((a, b) => Number(b.revenue_brl || 0) - Number(a.revenue_brl || 0));
                  } else if (partnerSortRevenue === "asc") {
                    list.sort((a, b) => Number(a.revenue_brl || 0) - Number(b.revenue_brl || 0));
                  } else {
                    // Padrão: Ordem alfabética de nomes de parceiros
                    list.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
                  }

                  if (list.length === 0) {
                    return <p className="text-sm text-muted-foreground p-4 text-center">Nenhum parceiro encontrado.</p>;
                  }

                  return (
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
                      {list.map((a) => {
                        const st = String(a.status || "active");
                        const revVal = Number(a.revenue_brl || 0);

                        return (
                          <Card
                            key={String(a.id)}
                            className="cursor-pointer hover:border-primary/60 transition-colors flex flex-col justify-between p-4 min-h-[120px] aspect-square group shadow-sm hover:shadow-md"
                            onClick={() => setPartnerDetailModal(a)}
                          >
                            <div className="space-y-2">
                              <div className="flex items-start justify-between gap-1">
                                <span className="font-semibold text-sm line-clamp-2 group-hover:text-primary transition-colors">
                                  {String(a.name)}
                                </span>
                                <span
                                  className={`shrink-0 text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                                    st === "active"
                                      ? "bg-emerald-500/10 text-emerald-600"
                                      : st === "paused"
                                      ? "bg-amber-500/10 text-amber-600"
                                      : st === "pending"
                                      ? "bg-blue-500/10 text-blue-600"
                                      : "bg-red-500/10 text-red-600"
                                  }`}
                                >
                                  {st === "active" ? "Ativo" : st === "paused" ? "Pausado" : st === "pending" ? "Pendente" : "Rejeitado"}
                                </span>
                              </div>
                              <div className="text-xs font-mono text-muted-foreground uppercase">{String(a.code)}</div>
                            </div>

                            <div className="pt-3 border-t flex flex-col items-start gap-0.5">
                              <span className="text-[10px] text-muted-foreground uppercase font-medium">Receita Gerada</span>
                              <span className="text-sm font-bold font-mono text-emerald-600">
                                R$ {revVal.toFixed(2)}
                              </span>
                            </div>
                          </Card>
                        );
                      })}
                    </div>
                  );
                })()}

                {/* Modal de Detalhes do Parceiro */}
                {partnerDetailModal && (
                  <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
                    <Card className="w-full max-w-lg space-y-4 p-6 shadow-xl animate-in fade-in zoom-in-95">
                      <div className="flex justify-between items-start border-b pb-3">
                        <div>
                          <h2 className="text-xl font-bold">{String(partnerDetailModal.name)}</h2>
                          <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground mt-0.5">
                            <span>Código: {String(partnerDetailModal.code)}</span>
                            <span>·</span>
                            <span className="capitalize">Status: {String(partnerDetailModal.status)}</span>
                          </div>
                        </div>
                        <Button size="sm" variant="ghost" onClick={() => setPartnerDetailModal(null)}>✕</Button>
                      </div>

                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <div className="space-y-1">
                          <span className="text-muted-foreground block">E-mail:</span>
                          <span className="font-medium break-all">{String(partnerDetailModal.contact_email || "—")}</span>
                        </div>
                        <div className="space-y-1">
                          <span className="text-muted-foreground block">Telefone:</span>
                          <span className="font-medium">{String(partnerDetailModal.contact_phone || "—")}</span>
                        </div>
                        <div className="space-y-1">
                          <span className="text-muted-foreground block">CPF:</span>
                          <span className="font-medium font-mono">{String(partnerDetailModal.cpf || "—")}</span>
                        </div>
                        <div className="space-y-1">
                          <span className="text-muted-foreground block">Tipo de Pagamento:</span>
                          <span className="font-medium uppercase">{String(partnerDetailModal.payment_type || "—")}</span>
                        </div>
                        <div className="space-y-1">
                          <span className="text-muted-foreground block">Comissão (%):</span>
                          <span className="font-medium">{String(partnerDetailModal.commission_pct || "20")}%</span>
                        </div>
                        <div className="space-y-1">
                          <span className="text-muted-foreground block">Desconto Cupom (%):</span>
                          <span className="font-medium">{String(partnerDetailModal.discount_pcts || "10")}%</span>
                        </div>
                        <div className="space-y-1 bg-emerald-500/5 p-2 rounded border border-emerald-500/20 col-span-2">
                          <span className="text-muted-foreground block">Receita Gerada:</span>
                          <span className="font-bold text-sm text-emerald-600 font-mono">
                            R$ {Number(partnerDetailModal.revenue_brl || 0).toFixed(2)}
                          </span>
                        </div>
                        <div className="space-y-1 bg-muted/40 p-2 rounded">
                          <span className="text-muted-foreground block">Comissão Devida:</span>
                          <span className="font-bold font-mono">R$ {String(partnerDetailModal.commission_due_brl || "0.00")}</span>
                        </div>
                        <div className="space-y-1 bg-muted/40 p-2 rounded">
                          <span className="text-muted-foreground block">Comissão Paga:</span>
                          <span className="font-bold font-mono">R$ {String(partnerDetailModal.commission_paid_brl || "0.00")}</span>
                        </div>
                      </div>

                      <div className="pt-3 border-t flex flex-wrap gap-2 justify-end">
                        {partnerDetailModal.status === "pending" && (
                          <>
                            <Button size="sm" onClick={() => { approveAffiliate(partnerDetailModal); setPartnerDetailModal(null); }}>Aprovar</Button>
                            <Button size="sm" variant="destructive" onClick={() => { openReject(partnerDetailModal); setPartnerDetailModal(null); }}>Rejeitar</Button>
                          </>
                        )}
                        {partnerDetailModal.status === "active" && (
                          <>
                            <Button size="sm" variant="outline" onClick={() => resendInvite(partnerDetailModal)}>Reenviar convite</Button>
                            <Button size="sm" variant="outline" onClick={() => { openAffPayment(partnerDetailModal); setPartnerDetailModal(null); }}>Registrar pagamento</Button>
                            <Button size="sm" variant="outline" onClick={() => { openAffPaymentsList(partnerDetailModal); setPartnerDetailModal(null); }}>Ver pagamentos</Button>
                          </>
                        )}
                        {(partnerDetailModal.status === "active" || partnerDetailModal.status === "paused") && (
                          <Button
                            size="sm"
                            variant={partnerDetailModal.status === "active" ? "secondary" : "default"}
                            onClick={async () => {
                              const newSt = partnerDetailModal.status === "active" ? "paused" : "active";
                              await adminApi.patchAffiliate(String(partnerDetailModal.id), { status: newSt });
                              setPartnerDetailModal(null);
                              await loadAffiliates();
                            }}
                          >
                            {partnerDetailModal.status === "active" ? "Pausar" : "Ativar"}
                          </Button>
                        )}
                        <Button size="sm" variant="destructive" onClick={() => { deleteAffiliate(partnerDetailModal); setPartnerDetailModal(null); }}>
                          Excluir
                        </Button>
                      </div>
                    </Card>
                  </div>
                )}

                <div className="rounded-lg border p-4">
                  <div className="text-sm font-medium mb-2">Janela de atribuição de parceiro</div>
                  <p className="text-xs text-muted-foreground mb-3">Por quantos dias um clique no link do parceiro continua valendo para atribuir a comissão de uma compra futura (o cupom do parceiro atribui na hora, independente dessa janela).</p>
                  <form onSubmit={saveAttributionDays} className="flex flex-wrap gap-2 items-end">
                    <Field label="Dias"><Input className="w-32" type="number" min="1" value={attributionDays} onChange={(e) => setAttributionDays(e.target.value)} required /></Field>
                    <Button type="submit" size="sm">Salvar</Button>
                  </form>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle className="text-lg">Conta demo — uso por CPF</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  Quantas análises cada CPF gerou usando a conta demo compartilhada (aproximado por janela de
                  sessão entre logins) — útil para flagrar parceiro revendendo análises por fora.
                </p>
                <div className="overflow-x-auto rounded-lg border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-xs text-muted-foreground">
                      <tr>
                        <th className="text-left font-medium px-3 py-2">CPF</th>
                        <th className="text-left font-medium px-3 py-2">Parceiro</th>
                        <th className="text-right font-medium px-3 py-2">Logins</th>
                        <th className="text-right font-medium px-3 py-2">Análises</th>
                        <th className="text-right font-medium px-3 py-2">Último acesso</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {demoUsage.map((d) => (
                        <tr key={String(d.cpf)} className="hover:bg-muted/30">
                          <td className="px-3 py-2 font-mono text-xs">{String(d.cpf)}</td>
                          <td className="px-3 py-2">{String(d.affiliate_name ?? "—")}</td>
                          <td className="px-3 py-2 text-right">{Number(d.logins)}</td>
                          <td className="px-3 py-2 text-right font-semibold">{Number(d.analyses)}</td>
                          <td className="px-3 py-2 text-right text-xs text-muted-foreground">{fmt(String(d.last_login_at))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {demoUsage.length === 0 && <p className="text-sm text-muted-foreground p-3">Nenhum acesso à conta demo registrado ainda.</p>}
                </div>
              </CardContent>
            </Card>

            <Modal open={!!rejectModal} onClose={() => setRejectModal(null)} title={`Rejeitar solicitação — ${rejectModal?.name ?? ""}`}>
              <form onSubmit={submitReject} className="space-y-3">
                <Field label="Motivo (opcional, fica registrado)">
                  <Textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={3} />
                </Field>
                <Button type="submit" variant="destructive" className="w-full">Confirmar rejeição</Button>
              </form>
            </Modal>
          </TabsContent>
        )}

        {/* ---------------- Documentos legais ---------------- */}
        {isOwner && (
          <TabsContent value="documentos">
            <Card>
              <CardHeader><CardTitle className="text-lg">Documentos que os usuários assinam</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Editar e publicar aqui cria uma NOVA versão vigente e revoga o aceite de todos os
                  usuários — na próxima vez que logarem, será pedido que revisem e assinem novamente.
                </p>
                {legalMsg && <div className="text-sm rounded-md bg-emerald-500/10 text-emerald-600 p-3">{legalMsg}</div>}
                <div className="divide-y text-sm">
                  {legalDocs.map((d) => (
                    <div key={d.id} className="flex items-center justify-between py-2.5 gap-2">
                      <div className="min-w-0">
                        <div className="font-medium">{d.title}</div>
                        <div className="text-xs text-muted-foreground">
                          {d.type} · versão {d.version}{d.published_at ? ` · publicado em ${fmt(d.published_at)}` : ""}
                        </div>
                      </div>
                      <Button size="sm" variant="outline" onClick={() => openEditLegal(d)}>Editar</Button>
                    </div>
                  ))}
                  {legalDocs.length === 0 && <p className="text-sm text-muted-foreground">Nenhum documento cadastrado.</p>}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}

        {/* ---------------- Configurações ---------------- */}
        {isOwner && (
          <TabsContent value="config">
            <Card>
              <CardHeader><CardTitle className="text-lg">Configurações da plataforma</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">A janela de atribuição de afiliados agora é configurada na aba Afiliados. Aqui ficam as demais configurações gerais do site (chave/valor em JSON).</p>
                <form onSubmit={saveSetting} className="flex flex-wrap gap-2 items-end">
                  <Field label="Chave"><Input className="w-64" placeholder="ex: suporte_email" value={newSetting.key} onChange={(e) => setNewSetting({ ...newSetting, key: e.target.value })} required /></Field>
                  <Field label="Valor (texto ou JSON)" className="flex-1 min-w-56"><Input placeholder='ex: "contato@apostainfo.com.br" ou {"dias": 30}' value={newSetting.value} onChange={(e) => setNewSetting({ ...newSetting, value: e.target.value })} required /></Field>
                  <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Salvar</Button>
                </form>
                <div className="divide-y text-sm">
                  {settings.filter((s) => s.key !== "affiliate_attribution_days").map((s) => (
                    <div key={String(s.key)} className="flex justify-between py-2">
                      <span className="font-mono text-xs">{String(s.key)}</span>
                      <span className="text-xs text-muted-foreground">{JSON.stringify(s.value)}</span>
                    </div>
                  ))}
                  {settings.filter((s) => s.key !== "affiliate_attribution_days").length === 0 && <p className="text-sm text-muted-foreground">Nenhuma configuração definida (usa os defaults do código).</p>}
                </div>
              </CardContent>
            </Card>

            {/* Gerenciar Conta de Teste */}
            <Card className="mt-6 border-amber-500/30 bg-amber-500/5">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Shield className="w-5 h-5 text-amber-500" />
                  Gerenciar Conta de Teste (teste@gmail.com)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-xs text-muted-foreground">
                  Altere manualmente a senha da conta de teste (<strong>teste@gmail.com</strong>). A nova senha será salva imediatamente e <strong>todas as sessões ativas desta conta serão revogadas (deslogando todos os usuários conectados a ela)</strong>.
                </p>
                {testAccountMsg && (
                  <div className="p-3 text-xs rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                    {testAccountMsg}
                  </div>
                )}
                <form onSubmit={resetTestAccount} className="flex flex-wrap gap-3 items-end max-w-lg">
                  <div className="flex-1 min-w-[200px] space-y-1.5">
                    <Label htmlFor="test-account-pass">Nova Senha</Label>
                    <Input
                      id="test-account-pass"
                      type="password"
                      placeholder="Digite a nova senha..."
                      value={testPassword}
                      onChange={(e) => setTestPassword(e.target.value)}
                      required
                      minLength={6}
                    />
                  </div>
                  <Button type="submit" variant="default" disabled={testAccountBusy} className="bg-amber-600 hover:bg-amber-700 text-white">
                    {testAccountBusy ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                    Resetar Senha e Deslogar Todos
                  </Button>
                </form>
              </CardContent>
            </Card>
          </TabsContent>
        )}


        {/* ---------------- Análise Aprofundada ---------------- */}
        <TabsContent value="deep">
          <Card>
            <CardHeader><CardTitle>Análise Aprofundada Detalhada</CardTitle></CardHeader>
            <CardContent>
              <form onSubmit={submitDeepAnalysis} className="space-y-4 max-w-2xl bg-muted/30 p-4 rounded-lg border border-border/50 mb-8">
                <div className="grid grid-cols-2 gap-4">
                  <Field label="Partida (Selecione a partida agendada)">
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full justify-start text-left"
                      onClick={() => setPickerDeepAnalysisOpen(true)}
                    >
                      {newDeepAnalysis.fixture_id
                        ? upcoming.find(f => String(f.fixture_id) === newDeepAnalysis.fixture_id)?.home
                          ? `${upcoming.find(f => String(f.fixture_id) === newDeepAnalysis.fixture_id)?.home} x ${upcoming.find(f => String(f.fixture_id) === newDeepAnalysis.fixture_id)?.away}`
                          : `ID: ${newDeepAnalysis.fixture_id}`
                        : "Selecionar Partida..."}
                    </Button>
                  </Field>
                  <Field label="Nome do Analista">
                    <Input required value={newDeepAnalysis.analyst_name} onChange={(e) => setNewDeepAnalysis({ ...newDeepAnalysis, analyst_name: e.target.value })} />
                  </Field>
                </div>
                <Field label="Conteúdo da Análise (Markdown)">
                  <Textarea className="min-h-[250px] font-mono text-xs" required value={newDeepAnalysis.markdown_content} onChange={(e) => setNewDeepAnalysis({ ...newDeepAnalysis, markdown_content: e.target.value })} />
                </Field>
                <div className="flex justify-end"><Button type="submit" size="sm"><Plus className="w-4 h-4 mr-1" /> Salvar / Atualizar Análise</Button></div>
              </form>

              <div className="space-y-3">
                {deepAnalyses.map(da => (
                  <div key={String(da.id)} className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-muted/30 transition-colors">
                    <div>
                      <div className="font-semibold text-sm">Partida ID: {String(da.fixture_id)}</div>
                      <div className="text-xs text-muted-foreground flex gap-3 mt-1">
                        <span>Analista: {String(da.analyst_name)}</span>
                        <span>Atualizado em: {fmt(String(da.updated_at))}</span>
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => setNewDeepAnalysis({ fixture_id: String(da.fixture_id), analyst_name: String(da.analyst_name), markdown_content: String(da.markdown_content) })}>Editar</Button>
                      <Button variant="destructive" size="sm" onClick={() => deleteDeepAnalysis(Number(da.fixture_id))}>Excluir</Button>
                    </div>
                  </div>
                ))}
                {deepAnalyses.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Nenhuma análise cadastrada.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---------------- Partidas em Destaque ---------------- */}
        <TabsContent value="destaque">
          <Card>
            <CardHeader><CardTitle>Partidas em Destaque na Home</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                Selecione até 10 partidas para substituir o banner padrão da home por cards
                clicáveis. Ao clicar num card, o visitante só precisa apertar &quot;Gerar Análise&quot;.
              </p>
              <div className="flex justify-end mb-4">
                <Button size="sm" disabled={featuredMatches.length >= 10} onClick={() => setPickerFeaturedOpen(true)}>
                  <Plus className="w-4 h-4 mr-1" /> Adicionar partida{featuredMatches.length >= 10 ? " (máximo 10)" : ""}
                </Button>
              </div>
              <div className="space-y-2">
                {featuredMatches.map((f, i) => (
                  <div key={f.id} className="flex items-center justify-between p-3 rounded-lg border bg-card hover:bg-muted/30 transition-colors gap-2">
                    <div className="min-w-0">
                      {f.fixture ? (
                        <>
                          <div className="font-semibold text-sm truncate">{f.fixture.home} x {f.fixture.away}</div>
                          <div className="text-xs text-muted-foreground">{f.fixture.tournament} · {fmt(f.fixture.date)}</div>
                        </>
                      ) : (
                        <div className="text-sm text-muted-foreground italic">Partida não encontrada mais nos próximos jogos (fixture_id: {f.fixture_id})</div>
                      )}
                    </div>
                    <div className="flex gap-1.5 shrink-0">
                      <Button variant="outline" size="sm" disabled={i === 0} onClick={() => moveFeaturedMatch(i, -1)}>↑</Button>
                      <Button variant="outline" size="sm" disabled={i === featuredMatches.length - 1} onClick={() => moveFeaturedMatch(i, 1)}>↓</Button>
                      <Button variant="destructive" size="sm" onClick={() => deleteFeaturedMatch(f.id)}>Excluir</Button>
                    </div>
                  </div>
                ))}
                {featuredMatches.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Nenhuma partida em destaque.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---------------- Compartilhar Análise ---------------- */}
        <TabsContent value="compartilhar">
          <Card>
            <CardHeader><CardTitle>Compartilhar Análise</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                Gere um link público de uma análise completa (sem &quot;Monte sua Seleção&quot;),
                usável como porta de entrada para visitantes sem cadastro.
              </p>
              <div className="flex justify-end mb-4">
                <Button size="sm" onClick={() => setPickerShareOpen(true)}><Plus className="w-4 h-4 mr-1" /> Nova partida</Button>
              </div>
              <div className="space-y-2">
                {sharedAnalyses.map((s) => {
                  const url = shareUrl(s.token);
                  return (
                    <div key={s.id} className="p-3 rounded-lg border bg-card hover:bg-muted/30 transition-colors space-y-2">
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div className="min-w-0">
                          <div className="font-semibold text-sm truncate">{s.home_team} x {s.away_team}</div>
                          <div className="text-xs text-muted-foreground">
                            {s.tournament} · gerado em {fmt(s.created_at)}{!s.active && " · inativo"}
                          </div>
                        </div>
                        <div className="flex gap-1.5 shrink-0">
                          <Button variant="outline" size="sm" onClick={() => copyShareUrl(url)}>Copiar link</Button>
                          <Button variant="destructive" size="sm" onClick={() => deleteSharedAnalysis(s.id)}>Excluir</Button>
                        </div>
                      </div>
                      <Input readOnly value={url} className="text-xs h-8" onFocus={(e) => e.target.select()} />
                    </div>
                  );
                })}
                {sharedAnalyses.length === 0 && <p className="text-sm text-muted-foreground text-center py-4">Nenhum link compartilhado ainda.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---------------- Auditoria ---------------- */}
        {isOwner && (
          <TabsContent value="auditoria">
            <Card>
              <CardHeader><CardTitle className="text-lg">Auditoria</CardTitle></CardHeader>
              <CardContent>
                <div className="divide-y text-sm">
                  {audit.map((a) => (
                    <div key={a.id} className="flex justify-between py-2 gap-2 flex-wrap">
                      <span className="font-mono text-xs">{a.action} {a.target_type ? `(${a.target_type})` : ""}</span>
                      <span className="text-xs text-muted-foreground">{a.admin_name ?? a.admin_email ?? "sistema"} · {fmt(a.created_at)}</span>
                    </div>
                  ))}
                  {audit.length === 0 && <p className="text-sm text-muted-foreground">Sem registros.</p>}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {/* ---------------- Modais ---------------- */}
      <ConfirmModal state={confirmState} onClose={() => setConfirmState(null)} />

      <Modal open={!!grantModal} onClose={() => setGrantModal(null)} title={`Ajustar créditos — ${grantModal?.email ?? ""}`}>
        <form onSubmit={submitGrant} className="space-y-3">
          <Field label="Quantidade (negativo para debitar)">
            <Input type="number" value={grantForm.amount} onChange={(e) => setGrantForm({ ...grantForm, amount: e.target.value })} required />
          </Field>
          <Field label="Motivo">
            <Input value={grantForm.reason} onChange={(e) => setGrantForm({ ...grantForm, reason: e.target.value })} required />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setGrantModal(null)}>Cancelar</Button>
            <Button type="submit" size="sm">Confirmar</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!editCouponModal} onClose={() => setEditCouponModal(null)} title={`Editar cupom — ${editCouponModal?.code ?? ""}`} wide>
        <form onSubmit={submitEditCoupon} className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Field label="Tipo de desconto">
            <select className="border rounded-md px-2 py-2 text-sm bg-background w-full" value={editCouponForm.discount_type}
                    onChange={(e) => setEditCouponForm({ ...editCouponForm, discount_type: e.target.value })}>
              <option value="percentage">% desconto</option>
              <option value="fixed">R$ desconto</option>
              <option value="bonus_credits">créditos bônus</option>
            </select>
          </Field>
          <Field label="Valor">
            <Input type="number" value={editCouponForm.discount_value} onChange={(e) => setEditCouponForm({ ...editCouponForm, discount_value: e.target.value })} required />
          </Field>
          <Field label="Compra mínima (R$)">
            <Input type="number" value={editCouponForm.min_purchase_brl} onChange={(e) => setEditCouponForm({ ...editCouponForm, min_purchase_brl: e.target.value })} />
          </Field>
          <Field label="Válido até">
            <Input type="date" value={editCouponForm.valid_to} onChange={(e) => setEditCouponForm({ ...editCouponForm, valid_to: e.target.value })} />
          </Field>
          <Field label="Limite de usos (total)">
            <Input type="number" value={editCouponForm.usage_limit} onChange={(e) => setEditCouponForm({ ...editCouponForm, usage_limit: e.target.value })} />
          </Field>
          <Field label="Limite por usuário">
            <Input type="number" value={editCouponForm.per_user_limit} onChange={(e) => setEditCouponForm({ ...editCouponForm, per_user_limit: e.target.value })} />
          </Field>
          <Field label="Regras/descrição" className="sm:col-span-2">
            <Textarea value={editCouponForm.description} onChange={(e) => setEditCouponForm({ ...editCouponForm, description: e.target.value })} />
          </Field>
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={editCouponForm.first_purchase_only} onChange={(e) => setEditCouponForm({ ...editCouponForm, first_purchase_only: e.target.checked })} />
            Só 1ª compra
          </label>
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={editCouponForm.active} onChange={(e) => setEditCouponForm({ ...editCouponForm, active: e.target.checked })} />
            Ativo
          </label>
          <div className="sm:col-span-2 flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditCouponModal(null)}>Cancelar</Button>
            <Button type="submit" size="sm">Salvar</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!editBannerModal} onClose={() => setEditBannerModal(null)} title="Editar banner">
        <form onSubmit={submitEditBanner} className="space-y-3">
          <Field label="Título"><Input value={editBannerForm.title} onChange={(e) => setEditBannerForm({ ...editBannerForm, title: e.target.value })} required /></Field>
          <Field label="Texto"><Textarea value={editBannerForm.body} onChange={(e) => setEditBannerForm({ ...editBannerForm, body: e.target.value })} /></Field>
          <Field label="Imagem de fundo (URL)"><Input value={editBannerForm.image_url} onChange={(e) => setEditBannerForm({ ...editBannerForm, image_url: e.target.value })} placeholder="https://..." /></Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setEditBannerModal(null)}>Cancelar</Button>
            <Button type="submit" size="sm">Salvar</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!editLegalModal} onClose={() => setEditLegalModal(null)} title={`Editar documento — ${editLegalModal?.title ?? ""}`} wide>
        {editLegalLoading ? (
          <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
        ) : (
          <form onSubmit={submitEditLegal} className="space-y-3">
            <p className="text-xs rounded-md bg-amber-500/10 text-amber-600 p-3">
              Publicar cria a versão {(editLegalModal?.version ?? 0) + 1} e revoga o aceite de
              todos os usuários da versão atual.
            </p>
            <Field label="Título"><Input value={editLegalForm.title} onChange={(e) => setEditLegalForm({ ...editLegalForm, title: e.target.value })} required /></Field>
            <Field label="Conteúdo (Markdown)">
              <Textarea className="min-h-[400px] font-mono text-xs" value={editLegalForm.body_md}
                        onChange={(e) => setEditLegalForm({ ...editLegalForm, body_md: e.target.value })} required />
            </Field>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setEditLegalModal(null)}>Cancelar</Button>
              <Button type="submit" size="sm">Publicar nova versão</Button>
            </div>
          </form>
        )}
      </Modal>

      <Modal open={!!affPaymentModal} onClose={() => setAffPaymentModal(null)} title={`Registrar pagamento — ${affPaymentModal?.name ?? ""}`}>
        <form onSubmit={submitAffPayment} className="space-y-3">
          <Field label="Valor pago (R$)"><Input type="number" step="0.01" value={affPaymentForm.amount_brl} onChange={(e) => setAffPaymentForm({ ...affPaymentForm, amount_brl: e.target.value })} required /></Field>
          <Field label="Método">
            <select className="border rounded-md px-2 py-2 text-sm bg-background w-full" value={affPaymentForm.method} onChange={(e) => setAffPaymentForm({ ...affPaymentForm, method: e.target.value })}>
              <option value="pix">Pix</option>
              <option value="transferencia">Transferência</option>
              <option value="outro">Outro</option>
            </select>
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setAffPaymentModal(null)}>Cancelar</Button>
            <Button type="submit" size="sm">Confirmar</Button>
          </div>
        </form>
      </Modal>

      <Modal open={!!affPaymentsListModal} onClose={() => setAffPaymentsListModal(null)} title={`Pagamentos — ${affPaymentsListModal?.affiliate.name ?? ""}`} wide>
        <div className="divide-y text-sm">
          {affPaymentsListModal?.items.map((p) => (
            <div key={String(p.id)} className="flex justify-between items-center py-2 gap-2 flex-wrap">
              <span className="font-mono">R$ {String(p.amount_brl)}</span>
              <span className="text-xs text-muted-foreground">{String(p.method ?? "—")} · {p.paid_at ? fmt(String(p.paid_at)) : "—"}</span>
              <span className="text-xs px-2 rounded bg-muted">{String(p.status)}</span>
            </div>
          ))}
          {affPaymentsListModal && affPaymentsListModal.items.length === 0 && <p className="text-sm text-muted-foreground py-2">Nenhum pagamento registrado ainda para este afiliado.</p>}
        </div>
      </Modal>

      <Modal open={!!campaignDashModal} onClose={() => setCampaignDashModal(null)} title={`Dashboard — ${campaignDashModal?.name ?? ""}`}>
        {campaignDashModal && (
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Receita</div><div className="font-bold">R$ {String(campaignDashModal.revenue_brl)}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Pedidos</div><div className="font-bold">{String(campaignDashModal.orders)}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Ticket médio</div><div className="font-bold">R$ {String(campaignDashModal.ticket_medio_brl)}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Desconto dado</div><div className="font-bold">R$ {String(campaignDashModal.discount_given_brl)}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Cupons usados</div><div className="font-bold">{String(campaignDashModal.coupons_used)}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Comissão de afiliados</div><div className="font-bold">R$ {String(campaignDashModal.affiliate_commission_brl)}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">ROI</div><div className="font-bold">{campaignDashModal.roi != null ? Number(campaignDashModal.roi).toFixed(2) : "n/d"}</div></div>
            <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Novos usuários</div><div className="font-bold">{String(campaignDashModal.new_users)}</div></div>
          </div>
        )}
      </Modal>

      <Modal
        open={!!pickerModal}
        onClose={() => setPickerModal(null)}
        title={
          pickerModal?.kind === "banner" ? "Selecionar banner" :
          pickerModal?.kind === "package" ? "Selecionar pacotes" :
          pickerModal?.kind === "coupon" ? "Selecionar cupons" : "Selecionar afiliados"
        }
        wide
      >
        {pickerModal && pickerCampaign && (
          <div className="space-y-1.5 max-h-96 overflow-y-auto">
            {pickerModal.kind === "banner" && (
              <>
                <button
                  onClick={() => pickCampaignBanner(pickerModal.campaignId, null)}
                  className={`w-full text-left text-sm rounded-md px-3 py-2 border ${!pickerCampaign.banner_id ? "border-primary bg-primary/10" : "border-border/50 hover:bg-muted"}`}
                >Nenhum</button>
                {banners.map((b) => (
                  <button key={String(b.id)}
                    onClick={() => pickCampaignBanner(pickerModal.campaignId, String(b.id))}
                    className={`w-full text-left text-sm rounded-md px-3 py-2 border ${pickerCampaign.banner_id === b.id ? "border-primary bg-primary/10" : "border-border/50 hover:bg-muted"}`}
                  >{String(b.title)}</button>
                ))}
                {banners.length === 0 && <p className="text-sm text-muted-foreground">Nenhum banner cadastrado.</p>}
              </>
            )}
            {pickerModal.kind === "package" && packages.map((p) => {
              const has = (pickerCampaign.package_ids as string[]).includes(String(p.id));
              return (
                <button key={String(p.id)} onClick={() => toggleCampaignPackage(pickerModal.campaignId, String(p.id), has)}
                  className={`w-full text-left text-sm rounded-md px-3 py-2 border flex items-center justify-between ${has ? "border-primary bg-primary/10" : "border-border/50 hover:bg-muted"}`}
                >
                  <span>{String(p.name)} <span className="text-xs text-muted-foreground">R$ {String(p.price_brl)}</span></span>
                  {has && <CheckCircle2 className="w-4 h-4 text-primary" />}
                </button>
              );
            })}
            {pickerModal.kind === "coupon" && coupons.map((c) => {
              const has = (pickerCampaign.coupon_ids as string[]).includes(String(c.id));
              return (
                <button key={String(c.id)} onClick={() => toggleCampaignCoupon(pickerModal.campaignId, String(c.id), has)}
                  className={`w-full text-left text-sm rounded-md px-3 py-2 border flex items-center justify-between ${has ? "border-primary bg-primary/10" : "border-border/50 hover:bg-muted"}`}
                >
                  <span>{String(c.code)}</span>
                  {has && <CheckCircle2 className="w-4 h-4 text-primary" />}
                </button>
              );
            })}
            {pickerModal.kind === "affiliate" && affiliates.map((a) => {
              const has = (pickerCampaign.affiliate_ids as string[]).includes(String(a.id));
              return (
                <button key={String(a.id)} onClick={() => toggleCampaignAffiliate(pickerModal.campaignId, String(a.id), has)}
                  className={`w-full text-left text-sm rounded-md px-3 py-2 border flex items-center justify-between ${has ? "border-primary bg-primary/10" : "border-border/50 hover:bg-muted"}`}
                >
                  <span>{String(a.name)} <span className="text-xs text-muted-foreground">({String(a.code)})</span></span>
                  {has && <CheckCircle2 className="w-4 h-4 text-primary" />}
                </button>
              );
            })}
          </div>
        )}
      </Modal>

      <MatchPickerModal
        open={pickerDeepAnalysisOpen}
        onOpenChange={setPickerDeepAnalysisOpen}
        fixtures={upcoming}
        teamIds={teamIds}
        onSelect={(fx) => { setNewDeepAnalysis({ ...newDeepAnalysis, fixture_id: String(fx.fixture_id) }); setPickerDeepAnalysisOpen(false); }}
        title="Selecionar Partida para Análise Aprofundada"
        defaultScope="selecao"
        allCompetitions={allCompetitions}
      />

      <MatchPickerModal
        open={pickerFeaturedOpen}
        onOpenChange={setPickerFeaturedOpen}
        fixtures={upcoming}
        teamIds={teamIds}
        onSelect={(fx) => { setPickerFeaturedOpen(false); addFeaturedMatch(fx); }}
        title="Selecionar Partida em Destaque"
        defaultScope="selecao"
        allCompetitions={allCompetitions}
      />

      <MatchPickerModal
        open={pickerShareOpen}
        onOpenChange={setPickerShareOpen}
        fixtures={upcoming}
        teamIds={teamIds}
        onSelect={(fx) => { setPickerShareOpen(false); addSharedAnalysis(fx); }}
        title="Selecionar Partida para Compartilhar"
        defaultScope="selecao"
        allCompetitions={allCompetitions}
      />
    </div>
  );
}
