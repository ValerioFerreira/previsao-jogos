"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Shield, Ban, CheckCircle2, Coins, Plus, X } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { adminApi, type AdminUser, type AuditEntry } from "@/lib/adminApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

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

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const isAdmin = user && (user.role === "admin" || user.role === "superadmin");

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
  const [settings, setSettings] = useState<Record<string, unknown>[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const [newPromo, setNewPromo] = useState({ code: "", name: "", type: "refund_if_lose" });
  const [newCoupon, setNewCoupon] = useState({
    promotion_id: "", code: "", discount_type: "percentage", discount_value: "10",
    min_purchase_brl: "", first_purchase_only: false, description: "", valid_days: "30",
  });
  const [newPackage, setNewPackage] = useState({ name: "", credits: "10", price_brl: "10.00", bonus_credits: "0" });
  const [newAffiliate, setNewAffiliate] = useState({ name: "", code: "", commission_pct: "10", contact_email: "", contact_phone: "" });
  const [newBanner, setNewBanner] = useState({ title: "", body: "", image_url: "", priority: "0", sort_order: "0" });
  const [newCampaign, setNewCampaign] = useState({ name: "", priority: "0" });
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
  const [affPaymentModal, setAffPaymentModal] = useState<Record<string, unknown> | null>(null);
  const [affPaymentForm, setAffPaymentForm] = useState({ amount_brl: "0", method: "pix" });
  const [affPaymentsListModal, setAffPaymentsListModal] = useState<{ affiliate: Record<string, unknown>; items: Record<string, unknown>[] } | null>(null);
  const [campaignDashModal, setCampaignDashModal] = useState<Record<string, unknown> | null>(null);
  const [pickerModal, setPickerModal] = useState<{ campaignId: string; kind: "banner" | "package" | "coupon" | "affiliate" } | null>(null);

  useEffect(() => { if (!loading && !isAdmin) router.replace("/"); }, [loading, isAdmin, router]);

  const loadUsers = useCallback(async (query = "") => {
    try { setUsers((await adminApi.users(query)).items); } catch (e) { setErr((e as Error).message); }
  }, []);

  const loadAll = useCallback(async () => {
    await loadUsers();
    try {
      const [p, pr, a, d, cp, ca, pk, af, bn, cm, st] = await Promise.all([
        adminApi.payments(), adminApi.promotions(), adminApi.audit(), adminApi.dashboard(),
        adminApi.coupons(), adminApi.couponAnalytics(), adminApi.packages(), adminApi.affiliates(),
        adminApi.banners(), adminApi.campaigns(), adminApi.settings(),
      ]);
      setPayments(p.items); setPromos(pr.items); setAudit(a.items); setDashboard(d);
      setCoupons(cp.items); setCouponAnalytics(ca.items); setPackages(pk.items); setAffiliates(af.items);
      setBanners(bn.items); setCampaigns(cm.items); setSettings(st.items);
    } catch (e) { setErr((e as Error).message); }
  }, [loadUsers]);

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

  async function createAffiliate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createAffiliate({ ...newAffiliate, commission_pct: Number(newAffiliate.commission_pct) });
      setNewAffiliate({ name: "", code: "", commission_pct: "10", contact_email: "", contact_phone: "" });
      setAffiliates((await adminApi.affiliates()).items);
    } catch (e) { setErr((e as Error).message); }
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

  if (loading || !isAdmin) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  const rev = dashboard?.revenue as Record<string, string> | undefined;
  const users_ = dashboard?.users as Record<string, number> | undefined;
  const credits_ = dashboard?.credits as Record<string, string> | undefined;
  const pickerCampaign = pickerModal ? campaigns.find((c) => String(c.id) === pickerModal.campaignId) : null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><Shield className="w-6 h-6 text-primary" /> Painel administrativo</h1>
      {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      <Tabs defaultValue="dashboard">
        <TabsList className="flex flex-wrap h-auto w-full gap-1">
          <TabsTrigger value="dashboard">Dashboard</TabsTrigger>
          <TabsTrigger value="usuarios">Usuários</TabsTrigger>
          <TabsTrigger value="financeiro">Financeiro</TabsTrigger>
          <TabsTrigger value="promocoes">Promoções</TabsTrigger>
          <TabsTrigger value="cupons">Cupons</TabsTrigger>
          <TabsTrigger value="pacotes">Pacotes</TabsTrigger>
          <TabsTrigger value="afiliados">Afiliados</TabsTrigger>
          <TabsTrigger value="banners">Banners</TabsTrigger>
          <TabsTrigger value="campanhas">Campanhas</TabsTrigger>
          <TabsTrigger value="config">Configurações</TabsTrigger>
          <TabsTrigger value="auditoria">Auditoria</TabsTrigger>
        </TabsList>

        {/* ---------------- Dashboard ---------------- */}
        <TabsContent value="dashboard">
          <Card>
            <CardContent className="space-y-4 pt-6">
              <RevenueChart rev={rev} />
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

        {/* ---------------- Usuários ---------------- */}
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
                    <div className="min-w-0">
                      <div className="font-medium truncate">{u.full_name} {u.role !== "user" && <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary">{u.role}</span>}</div>
                      <div className="text-xs text-muted-foreground truncate">{u.email} · {u.status} · {u.available_balance ?? "0"} créditos</div>
                    </div>
                    <div className="flex gap-1.5 shrink-0">
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

        {/* ---------------- Financeiro ---------------- */}
        <TabsContent value="financeiro">
          <Card>
            <CardHeader><CardTitle className="text-lg">Pagamentos ({payments.length})</CardTitle></CardHeader>
            <CardContent>
              <div className="divide-y text-sm">
                {payments.map((p) => (
                  <div key={String(p.id)} className="flex justify-between py-2">
                    <span className="text-xs text-muted-foreground">{fmt(String(p.created_at))}</span>
                    <span>R$ {String(p.amount_brl)} · {String(p.credits)} créditos</span>
                    <span className="text-xs px-2 rounded bg-muted">{String(p.status)}</span>
                  </div>
                ))}
                {payments.length === 0 && <p className="text-sm text-muted-foreground">Nenhum pagamento.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---------------- Promoções ---------------- */}
        <TabsContent value="promocoes">
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
        </TabsContent>

        {/* ---------------- Cupons ---------------- */}
        <TabsContent value="cupons">
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
        </TabsContent>

        {/* ---------------- Pacotes ---------------- */}
        <TabsContent value="pacotes">
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
        </TabsContent>

        {/* ---------------- Afiliados ---------------- */}
        <TabsContent value="afiliados">
          <Card>
            <CardHeader><CardTitle className="text-lg">Afiliados</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={createAffiliate} className="flex flex-wrap gap-2 items-end">
                <Field label="Nome" className="flex-1 min-w-40"><Input value={newAffiliate.name} onChange={(e) => setNewAffiliate({ ...newAffiliate, name: e.target.value })} required /></Field>
                <Field label="Código (link)"><Input className="w-32" value={newAffiliate.code} onChange={(e) => setNewAffiliate({ ...newAffiliate, code: e.target.value })} required /></Field>
                <Field label="Comissão (%)"><Input className="w-24" type="number" value={newAffiliate.commission_pct} onChange={(e) => setNewAffiliate({ ...newAffiliate, commission_pct: e.target.value })} /></Field>
                <Field label="E-mail de contato"><Input className="w-52" type="email" value={newAffiliate.contact_email} onChange={(e) => setNewAffiliate({ ...newAffiliate, contact_email: e.target.value })} /></Field>
                <Field label="Telefone de contato"><Input className="w-40" value={newAffiliate.contact_phone} onChange={(e) => setNewAffiliate({ ...newAffiliate, contact_phone: e.target.value })} /></Field>
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>

              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-xs text-muted-foreground">
                    <tr>
                      <th className="text-left font-medium px-3 py-2">Nome</th>
                      <th className="text-left font-medium px-3 py-2">Código</th>
                      <th className="text-left font-medium px-3 py-2">Contato</th>
                      <th className="text-right font-medium px-3 py-2">Comissão</th>
                      <th className="text-right font-medium px-3 py-2">Devida</th>
                      <th className="text-right font-medium px-3 py-2">Paga</th>
                      <th className="text-right font-medium px-3 py-2">Ações</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {affiliates.map((a) => (
                      <tr key={String(a.id)} className="hover:bg-muted/30 align-top">
                        <td className="px-3 py-2 font-medium">{String(a.name)} <span className="block text-[10px] text-muted-foreground">{a.status === "active" ? "ativo" : "pausado"}</span></td>
                        <td className="px-3 py-2 font-mono text-xs">{String(a.code)}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">
                          {a.contact_email ? <div>{String(a.contact_email)}</div> : null}
                          {a.contact_phone ? <div>{String(a.contact_phone)}</div> : null}
                          {!a.contact_email && !a.contact_phone && "—"}
                        </td>
                        <td className="px-3 py-2 text-right">{a.commission_pct ? `${String(a.commission_pct)}%` : "—"}</td>
                        <td className="px-3 py-2 text-right font-mono">R$ {String(a.commission_due_brl)}</td>
                        <td className="px-3 py-2 text-right font-mono">R$ {String(a.commission_paid_brl)}</td>
                        <td className="px-3 py-2">
                          <div className="flex flex-col gap-1 items-stretch">
                            <Button size="sm" variant="outline" onClick={() => openAffPayment(a)}>Registrar pagamento</Button>
                            <Button size="sm" variant="outline" onClick={() => openAffPaymentsList(a)}>Ver pagamentos</Button>
                            <Button size="sm" variant="outline" onClick={async () => { await adminApi.patchAffiliate(String(a.id), { status: a.status === "active" ? "paused" : "active" }); setAffiliates((await adminApi.affiliates()).items); }}>
                              {a.status === "active" ? "Pausar" : "Ativar"}
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {affiliates.length === 0 && <p className="text-sm text-muted-foreground p-3">Nenhum afiliado.</p>}
              </div>

              <div className="rounded-lg border p-4">
                <div className="text-sm font-medium mb-2">Janela de atribuição de afiliado</div>
                <p className="text-xs text-muted-foreground mb-3">Por quantos dias um clique no link de afiliado continua valendo para atribuir a comissão de uma compra futura.</p>
                <form onSubmit={saveAttributionDays} className="flex flex-wrap gap-2 items-end">
                  <Field label="Dias"><Input className="w-32" type="number" min="1" value={attributionDays} onChange={(e) => setAttributionDays(e.target.value)} required /></Field>
                  <Button type="submit" size="sm">Salvar</Button>
                </form>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---------------- Banners ---------------- */}
        <TabsContent value="banners">
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
        </TabsContent>

        {/* ---------------- Campanhas ---------------- */}
        <TabsContent value="campanhas">
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
        </TabsContent>

        {/* ---------------- Configurações ---------------- */}
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
        </TabsContent>

        {/* ---------------- Auditoria ---------------- */}
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
    </div>
  );
}
