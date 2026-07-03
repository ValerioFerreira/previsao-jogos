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
  const [err, setErr] = useState<string | null>(null);
  const [newPromo, setNewPromo] = useState({ code: "", name: "", type: "refund_if_lose" });

  useEffect(() => { if (!loading && !isAdmin) router.replace("/"); }, [loading, isAdmin, router]);

  const loadUsers = useCallback(async (query = "") => {
    try { setUsers((await adminApi.users(query)).items); } catch (e) { setErr((e as Error).message); }
  }, []);

  const loadAll = useCallback(async () => {
    await loadUsers();
    try {
      const [p, pr, a] = await Promise.all([adminApi.payments(), adminApi.promotions(), adminApi.audit()]);
      setPayments(p.items); setPromos(pr.items); setAudit(a.items);
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

  if (loading || !isAdmin) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><Shield className="w-6 h-6 text-primary" /> Painel administrativo</h1>
      {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      <Tabs defaultValue="usuarios">
        <TabsList className="grid grid-cols-4 w-full">
          <TabsTrigger value="usuarios">Usuários</TabsTrigger>
          <TabsTrigger value="financeiro">Financeiro</TabsTrigger>
          <TabsTrigger value="promocoes">Promoções</TabsTrigger>
          <TabsTrigger value="auditoria">Auditoria</TabsTrigger>
        </TabsList>

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
