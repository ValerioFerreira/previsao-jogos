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
  const [packages, setPackages] = useState<Record<string, unknown>[]>([]);
  const [affiliates, setAffiliates] = useState<Record<string, unknown>[]>([]);
  const [banners, setBanners] = useState<Record<string, unknown>[]>([]);
  const [settings, setSettings] = useState<Record<string, unknown>[]>([]);
  const [err, setErr] = useState<string | null>(null);

  const [newPromo, setNewPromo] = useState({ code: "", name: "", type: "refund_if_lose" });
  const [newCoupon, setNewCoupon] = useState({ promotion_id: "", code: "", discount_type: "percentage", discount_value: "10" });
  const [newAffiliate, setNewAffiliate] = useState({ name: "", code: "", commission_pct: "10" });
  const [newBanner, setNewBanner] = useState({ title: "", body: "" });
  const [newSetting, setNewSetting] = useState({ key: "affiliate_attribution_days", value: "30" });

  useEffect(() => { if (!loading && !isAdmin) router.replace("/"); }, [loading, isAdmin, router]);

  const loadUsers = useCallback(async (query = "") => {
    try { setUsers((await adminApi.users(query)).items); } catch (e) { setErr((e as Error).message); }
  }, []);

  const loadAll = useCallback(async () => {
    await loadUsers();
    try {
      const [p, pr, a, d, cp, pk, af, bn, st] = await Promise.all([
        adminApi.payments(), adminApi.promotions(), adminApi.audit(), adminApi.dashboard(),
        adminApi.coupons(), adminApi.packages(), adminApi.affiliates(), adminApi.banners(), adminApi.settings(),
      ]);
      setPayments(p.items); setPromos(pr.items); setAudit(a.items); setDashboard(d);
      setCoupons(cp.items); setPackages(pk.items); setAffiliates(af.items); setBanners(bn.items); setSettings(st.items);
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
      });
      setNewCoupon({ promotion_id: "", code: "", discount_type: "percentage", discount_value: "10" });
      setCoupons((await adminApi.coupons()).items);
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
      await adminApi.createBanner(newBanner);
      setNewBanner({ title: "", body: "" });
      setBanners((await adminApi.banners()).items);
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
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {coupons.map((c) => (
                  <div key={String(c.id)} className="flex items-center justify-between py-2">
                    <span>{String(c.code)} <span className="text-xs text-muted-foreground">({String(c.discount_type)} · {c.redemptions as number} usos)</span></span>
                    <Button size="sm" variant="outline" onClick={async () => { await adminApi.patchCoupon(String(c.id), { active: !(c.active as boolean) }); setCoupons((await adminApi.coupons()).items); }}>
                      {(c.active as boolean) ? "Desativar" : "Ativar"}
                    </Button>
                  </div>
                ))}
                {coupons.length === 0 && <p className="text-sm text-muted-foreground">Nenhum cupom.</p>}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pacotes">
          <Card>
            <CardHeader><CardTitle className="text-lg">Pacotes de crédito</CardTitle></CardHeader>
            <CardContent>
              <div className="divide-y text-sm">
                {packages.map((p) => (
                  <div key={String(p.id)} className="flex items-center justify-between py-2 gap-2">
                    <span>{String(p.name)} <span className="text-xs text-muted-foreground">R$ {String(p.price_brl)} · {p.featured_badge ? String(p.featured_badge) : "sem selo"}</span></span>
                    <div className="flex gap-1.5">
                      {["mais_vendido", "melhor_oferta", "oferta_limitada"].map((b) => (
                        <Button key={b} size="sm" variant={p.featured_badge === b ? "default" : "outline"}
                               onClick={async () => { await adminApi.patchPackage(String(p.id), { featured_badge: p.featured_badge === b ? null : b }); setPackages((await adminApi.packages()).items); }}>
                          {b === "mais_vendido" ? "★" : b === "melhor_oferta" ? "$" : "⏱"}
                        </Button>
                      ))}
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
                  <div key={String(a.id)} className="flex items-center justify-between py-2">
                    <span>{String(a.name)} <span className="text-xs text-muted-foreground">({String(a.code)} · {String(a.commission_pct)}% · devida R$ {String(a.commission_due_brl)})</span></span>
                    <Button size="sm" variant="outline" onClick={async () => { await adminApi.patchAffiliate(String(a.id), { status: a.status === "active" ? "paused" : "active" }); setAffiliates((await adminApi.affiliates()).items); }}>
                      {a.status === "active" ? "Pausar" : "Ativar"}
                    </Button>
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
                <Button type="submit" size="sm"><Plus className="w-3.5 h-3.5 mr-1" /> Criar</Button>
              </form>
              <div className="divide-y text-sm">
                {banners.map((b) => (
                  <div key={String(b.id)} className="py-2">
                    <div className="font-medium">{String(b.title)}</div>
                    {!!b.body && <div className="text-xs text-muted-foreground">{String(b.body)}</div>}
                  </div>
                ))}
                {banners.length === 0 && <p className="text-sm text-muted-foreground">Nenhum banner.</p>}
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
