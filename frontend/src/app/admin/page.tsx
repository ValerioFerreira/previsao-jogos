"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Shield, Ban, CheckCircle2, Coins, Plus } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { adminApi, type AdminUser, type AuditEntry } from "@/lib/adminApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

function fmt(d: string) { return new Date(d).toLocaleString("pt-BR"); }

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
    min_purchase_brl: "", first_purchase_only: false, description: "", valid_to: "",
  });
  const [newPackage, setNewPackage] = useState({ name: "", credits: "10", price_brl: "10.00", bonus_credits: "0" });
  const [newAffiliate, setNewAffiliate] = useState({ name: "", code: "", commission_pct: "10" });
  const [newBanner, setNewBanner] = useState({ title: "", body: "", priority: "0", sort_order: "0" });
  const [newCampaign, setNewCampaign] = useState({ name: "", priority: "0" });
  const [newSetting, setNewSetting] = useState({ key: "affiliate_attribution_days", value: "30" });

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

  async function toggleBlock(u: AdminUser) {
    if (u.status === "blocked") await adminApi.unblock(u.id);
    else await adminApi.block(u.id, "bloqueado pelo admin");
    await loadUsers(q);
  }

  async function grant(u: AdminUser) {
    const amount = window.prompt(`Créditos para ${u.email} (use negativo para debitar):`, "10");
    if (!amount) return;
    const reason = window.prompt("Motivo:", "cortesia") || "ajuste admin";
    try {
      await adminApi.adjustCredits(u.id, { amount, kind: Number(amount) >= 0 ? "bonus" : "manual_adjustment", reason });
      await loadUsers(q);
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
        valid_to: newCoupon.valid_to || undefined,
        description: newCoupon.description || undefined,
      });
      setNewCoupon({ promotion_id: "", code: "", discount_type: "percentage", discount_value: "10",
        min_purchase_brl: "", first_purchase_only: false, description: "", valid_to: "" });
      setCoupons((await adminApi.coupons()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function editCoupon(c: Record<string, unknown>) {
    const description = window.prompt("Regras/descrição do cupom:", String(c.description ?? "")) ?? String(c.description ?? "");
    const discount_value = window.prompt("Valor do desconto (%, R$ ou créditos):", String(c.discount_value ?? c.bonus_credits ?? ""));
    if (discount_value === null) return;
    try {
      const patch: Record<string, unknown> = { description };
      if (c.discount_type === "bonus_credits") patch.bonus_credits = Number(discount_value);
      else patch.discount_value = Number(discount_value);
      await adminApi.patchCoupon(String(c.id), patch);
      setCoupons((await adminApi.coupons()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function deleteCoupon(c: Record<string, unknown>) {
    if (!window.confirm(`Excluir o cupom ${c.code}?`)) return;
    try {
      await adminApi.deleteCoupon(String(c.id));
      setCoupons((await adminApi.coupons()).items);
    } catch (e) { setErr((e as Error).message); }
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
      setNewAffiliate({ name: "", code: "", commission_pct: "10" });
      setAffiliates((await adminApi.affiliates()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function createBanner(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.createBanner({
        title: newBanner.title, body: newBanner.body,
        priority: Number(newBanner.priority), sort_order: Number(newBanner.sort_order),
      });
      setNewBanner({ title: "", body: "", priority: "0", sort_order: "0" });
      setBanners((await adminApi.banners()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function toggleBanner(b: Record<string, unknown>) {
    try {
      await adminApi.patchBanner(String(b.id), { active: !(b.active as boolean) });
      setBanners((await adminApi.banners()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function editBanner(b: Record<string, unknown>) {
    const title = window.prompt("Título:", String(b.title ?? "")) ?? String(b.title ?? "");
    const body = window.prompt("Texto:", String(b.body ?? "")) ?? String(b.body ?? "");
    try {
      await adminApi.patchBanner(String(b.id), { title, body });
      setBanners((await adminApi.banners()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function deleteBanner(b: Record<string, unknown>) {
    if (!window.confirm(`Excluir o banner "${b.title}"?`)) return;
    try {
      await adminApi.deleteBanner(String(b.id));
      setBanners((await adminApi.banners()).items);
    } catch (e) { setErr((e as Error).message); }
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

  async function deleteCampaign(c: Record<string, unknown>) {
    if (!window.confirm(`Excluir a campanha "${c.name}"?`)) return;
    try {
      await adminApi.deleteCampaign(String(c.id));
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function attachCampaignBanner(c: Record<string, unknown>) {
    const bannerId = window.prompt("ID do banner a associar (deixe vazio pra remover):",
      String(c.banner_id ?? ""));
    if (bannerId === null) return;
    try {
      await adminApi.patchCampaign(String(c.id), { banner_id: bannerId || null });
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function attachCampaignPackage(c: Record<string, unknown>) {
    const packageId = window.prompt("ID do pacote a incluir na campanha:");
    if (!packageId) return;
    try {
      await adminApi.addCampaignPackage(String(c.id), packageId);
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function attachCampaignCoupon(c: Record<string, unknown>) {
    const couponId = window.prompt("ID do cupom a incluir na campanha:");
    if (!couponId) return;
    try {
      await adminApi.addCampaignCoupon(String(c.id), couponId);
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function attachCampaignAffiliate(c: Record<string, unknown>) {
    const affiliateId = window.prompt("ID do afiliado a incluir na campanha:");
    if (!affiliateId) return;
    try {
      await adminApi.addCampaignAffiliate(String(c.id), affiliateId);
      setCampaigns((await adminApi.campaigns()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function viewCampaignDashboard(c: Record<string, unknown>) {
    try {
      const d = await adminApi.campaignDashboard(String(c.id));
      window.alert(
        `Campanha: ${c.name}\nReceita: R$ ${d.revenue_brl}\nPedidos: ${d.orders}\n` +
        `Ticket médio: R$ ${d.ticket_medio_brl}\nDesconto dado: R$ ${d.discount_given_brl}\n` +
        `Cupons usados: ${d.coupons_used}\nComissão de afiliados: R$ ${d.affiliate_commission_brl}\n` +
        `ROI: ${d.roi ?? "n/d"}\nNovos usuários no período: ${d.new_users}`
      );
    } catch (e) { setErr((e as Error).message); }
  }

  async function registerAffiliatePayment(a: Record<string, unknown>) {
    const amount = window.prompt(`Valor pago ao afiliado ${a.name} (R$):`, String(a.commission_due_brl ?? "0"));
    if (!amount) return;
    const method = window.prompt("Método (pix/transferência/...):", "pix") || "pix";
    try {
      await adminApi.createAffiliatePayment(String(a.id), { amount_brl: Number(amount), method });
      setAffiliates((await adminApi.affiliates()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  async function saveSetting(e: React.FormEvent) {
    e.preventDefault();
    try {
      await adminApi.setSetting(newSetting.key, { value: { days: Number(newSetting.value) } });
      setSettings((await adminApi.settings()).items);
    } catch (e) { setErr((e as Error).message); }
  }

  if (loading || !isAdmin) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  const rev = dashboard?.revenue as Record<string, string> | undefined;
  const users_ = dashboard?.users as Record<string, number> | undefined;
  const credits_ = dashboard?.credits as Record<string, string> | undefined;

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

        <TabsContent value="dashboard">
          <Card>
            <CardHeader><CardTitle className="text-lg">Dashboard executivo</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Hoje</div><div className="text-xl font-bold">R$ {rev?.today_brl ?? "0"}</div></div>
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Mês</div><div className="text-xl font-bold">R$ {rev?.month_brl ?? "0"}</div></div>
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Ano</div><div className="text-xl font-bold">R$ {rev?.year_brl ?? "0"}</div></div>
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Ticket médio</div><div className="text-xl font-bold">R$ {rev?.ticket_medio_brl ?? "0"}</div></div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Créditos vendidos</div><div className="text-xl font-bold">{credits_?.vendidos ?? "0"}</div></div>
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Créditos promo</div><div className="text-xl font-bold">{credits_?.promocionais ?? "0"}</div></div>
                <div className="rounded-lg border p-3"><div className="text-xs text-muted-foreground">Usuários ativos (30d)</div><div className="text-xl font-bold">{users_?.active_30d ?? 0}</div></div>
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
                      <Button size="sm" variant="outline" onClick={() => grant(u)}><Coins className="w-3.5 h-3.5" /></Button>
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

        <TabsContent value="promocoes">
          <Card>
            <CardHeader><CardTitle className="text-lg">Promoções</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={createPromo} className="flex flex-wrap gap-2 items-end">
                <Input className="w-32" placeholder="Código" value={newPromo.code} onChange={(e) => setNewPromo({ ...newPromo, code: e.target.value })} required />
                <Input className="flex-1 min-w-40" placeholder="Nome" value={newPromo.name} onChange={(e) => setNewPromo({ ...newPromo, name: e.target.value })} required />
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

        <TabsContent value="cupons">
          <Card>
            <CardHeader><CardTitle className="text-lg">Cupons</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">Todo cupom precisa de uma promoção existente (crie na aba Promoções primeiro e cole o ID abaixo).</p>
              <form onSubmit={createCoupon} className="flex flex-wrap gap-2 items-end">
                <Input className="w-56" placeholder="ID da promoção" value={newCoupon.promotion_id} onChange={(e) => setNewCoupon({ ...newCoupon, promotion_id: e.target.value })} required />
                <Input className="w-28" placeholder="Código" value={newCoupon.code} onChange={(e) => setNewCoupon({ ...newCoupon, code: e.target.value })} required />
                <select className="border rounded-md px-2 py-2 text-sm bg-background" value={newCoupon.discount_type} onChange={(e) => setNewCoupon({ ...newCoupon, discount_type: e.target.value })}>
                  <option value="percentage">% desconto</option>
                  <option value="fixed">R$ desconto</option>
                  <option value="bonus_credits">créditos bônus</option>
                </select>
                <Input className="w-24" type="number" placeholder="Valor" value={newCoupon.discount_value} onChange={(e) => setNewCoupon({ ...newCoupon, discount_value: e.target.value })} required />
                <Input className="w-32" type="number" placeholder="Compra mín. R$" value={newCoupon.min_purchase_brl} onChange={(e) => setNewCoupon({ ...newCoupon, min_purchase_brl: e.target.value })} />
                <Input className="w-40" type="date" placeholder="Válido até" value={newCoupon.valid_to} onChange={(e) => setNewCoupon({ ...newCoupon, valid_to: e.target.value })} />
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={newCoupon.first_purchase_only} onChange={(e) => setNewCoupon({ ...newCoupon, first_purchase_only: e.target.checked })} />
                  só 1ª compra
                </label>
                <Input className="flex-1 min-w-48" placeholder="Regras/descrição (texto livre)" value={newCoupon.description} onChange={(e) => setNewCoupon({ ...newCoupon, description: e.target.value })} />
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
                      <Button size="sm" variant="outline" onClick={() => editCoupon(c)}>Editar</Button>
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
                <div className="text-sm font-medium mb-2 mt-4">Analytics por cupom</div>
                <div className="divide-y text-sm">
                  {couponAnalytics.map((a) => (
                    <div key={String(a.coupon_id)} className="flex justify-between py-1.5 flex-wrap gap-x-4">
                      <span className="font-medium">{String(a.code)}</span>
                      <span className="text-xs text-muted-foreground">
                        receita R$ {String(a.revenue_brl)} · desconto R$ {String(a.discount_given_brl)} ·
                        ticket médio R$ {String(a.ticket_medio_brl)} · pedidos {a.orders_paid as number} ·
                        ROI {a.roi != null ? Number(a.roi).toFixed(2) : "n/d"}
                      </span>
                    </div>
                  ))}
                  {couponAnalytics.length === 0 && <p className="text-sm text-muted-foreground">Sem dados ainda.</p>}
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pacotes">
          <Card>
            <CardHeader><CardTitle className="text-lg">Pacotes de crédito</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">Pacotes nunca são excluídos fisicamente (pedidos antigos dependem deles) — use o status ativo/oculto/arquivado.</p>
              <form onSubmit={createPackage} className="flex flex-wrap gap-2 items-end">
                <Input className="flex-1 min-w-40" placeholder="Nome" value={newPackage.name} onChange={(e) => setNewPackage({ ...newPackage, name: e.target.value })} required />
                <Input className="w-24" type="number" placeholder="Créditos" value={newPackage.credits} onChange={(e) => setNewPackage({ ...newPackage, credits: e.target.value })} required />
                <Input className="w-28" type="number" step="0.01" placeholder="Preço R$" value={newPackage.price_brl} onChange={(e) => setNewPackage({ ...newPackage, price_brl: e.target.value })} required />
                <Input className="w-24" type="number" placeholder="Bônus" value={newPackage.bonus_credits} onChange={(e) => setNewPackage({ ...newPackage, bonus_credits: e.target.value })} />
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

        <TabsContent value="afiliados">
          <Card>
            <CardHeader><CardTitle className="text-lg">Afiliados</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={createAffiliate} className="flex flex-wrap gap-2 items-end">
                <Input className="flex-1 min-w-40" placeholder="Nome" value={newAffiliate.name} onChange={(e) => setNewAffiliate({ ...newAffiliate, name: e.target.value })} required />
                <Input className="w-32" placeholder="Código (link)" value={newAffiliate.code} onChange={(e) => setNewAffiliate({ ...newAffiliate, code: e.target.value })} required />
                <Input className="w-24" type="number" placeholder="Comissão %" value={newAffiliate.commission_pct} onChange={(e) => setNewAffiliate({ ...newAffiliate, commission_pct: e.target.value })} />
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {affiliates.map((a) => (
                  <div key={String(a.id)} className="flex items-center justify-between py-2 gap-2 flex-wrap">
                    <span>{String(a.name)} <span className="text-xs text-muted-foreground">({String(a.code)} · {String(a.commission_pct)}% · devida R$ {String(a.commission_due_brl)} · paga R$ {String(a.commission_paid_brl)})</span></span>
                    <div className="flex gap-1.5">
                      <Button size="sm" variant="outline" onClick={() => registerAffiliatePayment(a)}>Registrar pagamento</Button>
                      <Button size="sm" variant="outline" onClick={async () => { await adminApi.patchAffiliate(String(a.id), { status: a.status === "active" ? "paused" : "active" }); setAffiliates((await adminApi.affiliates()).items); }}>
                        {a.status === "active" ? "Pausar" : "Ativar"}
                      </Button>
                    </div>
                  </div>
                ))}
                {affiliates.length === 0 && <p className="text-sm text-muted-foreground">Nenhum afiliado.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="banners">
          <Card>
            <CardHeader><CardTitle className="text-lg">Banners promocionais</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={createBanner} className="flex flex-wrap gap-2 items-end">
                <Input className="w-56" placeholder="Título" value={newBanner.title} onChange={(e) => setNewBanner({ ...newBanner, title: e.target.value })} required />
                <Input className="flex-1 min-w-40" placeholder="Texto" value={newBanner.body} onChange={(e) => setNewBanner({ ...newBanner, body: e.target.value })} />
                <Input className="w-24" type="number" placeholder="Prioridade" value={newBanner.priority} onChange={(e) => setNewBanner({ ...newBanner, priority: e.target.value })} />
                <Input className="w-24" type="number" placeholder="Ordem" value={newBanner.sort_order} onChange={(e) => setNewBanner({ ...newBanner, sort_order: e.target.value })} />
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {banners.map((b) => (
                  <div key={String(b.id)} className="flex items-center justify-between py-2 gap-2 flex-wrap">
                    <div className="min-w-0">
                      <div className="font-medium">{String(b.title)} <span className="text-xs text-muted-foreground">(prioridade {String(b.priority)} · ordem {String(b.sort_order)} · {(b.active as boolean) ? "ativo" : "inativo"})</span></div>
                      {!!b.body && <div className="text-xs text-muted-foreground">{String(b.body)}</div>}
                    </div>
                    <div className="flex gap-1.5 shrink-0">
                      <Button size="sm" variant="outline" onClick={() => editBanner(b)}>Editar</Button>
                      <Button size="sm" variant="outline" onClick={() => toggleBanner(b)}>{(b.active as boolean) ? "Desativar" : "Ativar"}</Button>
                      <Button size="sm" variant="destructive" onClick={() => deleteBanner(b)}>Excluir</Button>
                    </div>
                  </div>
                ))}
                {banners.length === 0 && <p className="text-sm text-muted-foreground">Nenhum banner.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="campanhas">
          <Card>
            <CardHeader><CardTitle className="text-lg">Campanhas</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">Uma campanha amarra banner + cupons + pacotes + afiliados + período + prioridade. Associe pelos IDs (visíveis nas outras abas via inspeção da API por enquanto).</p>
              <form onSubmit={createCampaign} className="flex flex-wrap gap-2 items-end">
                <Input className="flex-1 min-w-40" placeholder="Nome" value={newCampaign.name} onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })} required />
                <Input className="w-24" type="number" placeholder="Prioridade" value={newCampaign.priority} onChange={(e) => setNewCampaign({ ...newCampaign, priority: e.target.value })} />
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {campaigns.map((c) => (
                  <div key={String(c.id)} className="py-3 space-y-1.5">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="font-medium">{String(c.name)} <span className="text-xs text-muted-foreground">(prioridade {String(c.priority)} · {(c.active as boolean) ? "ativa" : "inativa"})</span></span>
                      <div className="flex gap-1.5 shrink-0">
                        <Button size="sm" variant="outline" onClick={() => viewCampaignDashboard(c)}>Dashboard</Button>
                        <Button size="sm" variant="outline" onClick={() => toggleCampaign(c)}>{(c.active as boolean) ? "Desativar" : "Ativar"}</Button>
                        <Button size="sm" variant="destructive" onClick={() => deleteCampaign(c)}>Excluir</Button>
                      </div>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      banner: {String(c.banner_id ?? "nenhum")} · pacotes: {(c.package_ids as string[]).length} · cupons: {(c.coupon_ids as string[]).length} · afiliados: {(c.affiliate_ids as string[]).length}
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      <Button size="sm" variant="outline" onClick={() => attachCampaignBanner(c)}>+ banner</Button>
                      <Button size="sm" variant="outline" onClick={() => attachCampaignPackage(c)}>+ pacote</Button>
                      <Button size="sm" variant="outline" onClick={() => attachCampaignCoupon(c)}>+ cupom</Button>
                      <Button size="sm" variant="outline" onClick={() => attachCampaignAffiliate(c)}>+ afiliado</Button>
                    </div>
                  </div>
                ))}
                {campaigns.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma campanha.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="config">
          <Card>
            <CardHeader><CardTitle className="text-lg">Configurações da plataforma</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <form onSubmit={saveSetting} className="flex flex-wrap gap-2 items-end">
                <Input className="w-64" placeholder="Chave (ex: affiliate_attribution_days)" value={newSetting.key} onChange={(e) => setNewSetting({ ...newSetting, key: e.target.value })} required />
                <Input className="w-32" type="number" placeholder="Dias" value={newSetting.value} onChange={(e) => setNewSetting({ ...newSetting, value: e.target.value })} required />
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Salvar</Button>
              </form>
              <div className="divide-y text-sm">
                {settings.map((s) => (
                  <div key={String(s.key)} className="flex justify-between py-2">
                    <span className="font-mono text-xs">{String(s.key)}</span>
                    <span className="text-xs text-muted-foreground">{JSON.stringify(s.value)}</span>
                  </div>
                ))}
                {settings.length === 0 && <p className="text-sm text-muted-foreground">Nenhuma configuração definida (usa os defaults do código).</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="auditoria">
          <Card>
            <CardHeader><CardTitle className="text-lg">Auditoria</CardTitle></CardHeader>
            <CardContent>
              <div className="divide-y text-sm">
                {audit.map((a) => (
                  <div key={a.id} className="flex justify-between py-2">
                    <span className="font-mono text-xs">{a.action} {a.target_type ? `(${a.target_type})` : ""}</span>
                    <span className="text-xs text-muted-foreground">{fmt(a.created_at)}</span>
                  </div>
                ))}
                {audit.length === 0 && <p className="text-sm text-muted-foreground">Sem registros.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
