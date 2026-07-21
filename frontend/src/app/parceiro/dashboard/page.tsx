"use client";
import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2, Copy, TrendingUp, Users, ShoppingCart, DollarSign, Ticket, UserPlus, X } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import {
  affiliatesApi, type AffiliatePortalStats, type TimeseriesResponse,
  type CouponRequest, type ReferredPartnersResponse,
} from "@/lib/affiliatesApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function TimeseriesChart({ ts }: { ts: TimeseriesResponse }) {
  if (ts.items.length === 0) {
    return <p className="text-sm text-muted-foreground">Sem dados no período.</p>;
  }
  const max = Math.max(1, ...ts.items.map((p) => p.clicks));
  return (
    <div className="space-y-2">
      <div className="flex items-end gap-1 h-28">
        {ts.items.map((p) => (
          <div key={p.bucket} className="flex-1 flex flex-col items-center justify-end gap-1 group relative">
            <div
              className="w-full rounded-t bg-primary/70 group-hover:bg-primary transition-colors"
              style={{ height: `${Math.max(4, (p.clicks / max) * 100)}%` }}
              title={`${p.bucket}: ${p.clicks} cliques, ${p.conversions} conversões, R$ ${Number(p.revenue_brl).toFixed(2)}`}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>{ts.items[0].bucket}</span>
        <span>{ts.items[ts.items.length - 1].bucket}</span>
      </div>
    </div>
  );
}

export default function ParceiroDashboardPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<AffiliatePortalStats | null>(null);
  const [ts, setTs] = useState<TimeseriesResponse | null>(null);
  const [granularity, setGranularity] = useState<"day" | "month">("day");
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<"user" | "partner" | "code" | null>(null);
  const [couponReqs, setCouponReqs] = useState<CouponRequest[] | null>(null);
  const [referred, setReferred] = useState<ReferredPartnersResponse | null>(null);
  const [showCouponModal, setShowCouponModal] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    affiliatesApi.me().then(setStats).catch((e) => setErr((e as Error).message));
    affiliatesApi.listCouponRequests().then(setCouponReqs).catch(() => setCouponReqs([]));
    affiliatesApi.referredPartners().then(setReferred).catch(() => setReferred(null));
  }, [user]);

  useEffect(() => {
    if (!user) return;
    affiliatesApi.portalTimeseries(granularity).then(setTs).catch(() => setTs(null));
  }, [user, granularity]);

  function reloadCouponReqs() {
    affiliatesApi.listCouponRequests().then(setCouponReqs).catch(() => {});
  }

  function copy(value: string, which: "user" | "partner" | "code") {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(which);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  const partnerInviteLink =
    typeof window !== "undefined" && stats
      ? `${window.location.origin}/parceiro/solicitar?ref_partner=${stats.code}`
      : "";
  const pendingCoupon = couponReqs?.find((r) => r.status === "pending") || null;

  if (loading || (user && !stats && !err)) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  if (err) {
    return (
      <div className="max-w-2xl mx-auto text-sm rounded-md bg-red-500/10 text-red-600 p-4">
        {err.includes("parceiro") ? "Sua conta não é uma conta de parceiro." : err}
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <Link href="/parceiro" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="w-3.5 h-3.5" /> Voltar
        </Link>
        <h1 className="text-2xl font-bold mt-1">Dashboard do Parceiro</h1>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><Users className="w-4 h-4" /> Link para usuários</CardTitle>
            <p className="text-xs text-muted-foreground">Convide usuários. Na 1ª compra, seu cupom de desconto já vem preenchido e o usuário ganha 5 créditos promocionais.</p>
          </CardHeader>
          <CardContent className="flex items-center gap-2">
            <code className="flex-1 text-sm bg-muted rounded-md px-3 py-2 overflow-x-auto">{stats.link}</code>
            <Button size="sm" variant="outline" onClick={() => copy(stats.link, "user")}>
              <Copy className="w-3.5 h-3.5 mr-1" /> {copied === "user" ? "Copiado!" : "Copiar"}
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><UserPlus className="w-4 h-4" /> Link para indicar parceiros</CardTitle>
            <p className="text-xs text-muted-foreground">Convide novos parceiros. Você recebe {referred ? `${Number(referred.override_pct)}%` : "5%"} da comissão de cada parceiro que indicar (sem descontar dele).</p>
          </CardHeader>
          <CardContent className="flex items-center gap-2">
            <code className="flex-1 text-sm bg-muted rounded-md px-3 py-2 overflow-x-auto">{partnerInviteLink}</code>
            <Button size="sm" variant="outline" onClick={() => copy(partnerInviteLink, "partner")}>
              <Copy className="w-3.5 h-3.5 mr-1" /> {copied === "partner" ? "Copiado!" : "Copiar"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-lg">Seu código de desconto</CardTitle></CardHeader>
        <CardContent className="flex items-center gap-2">
          <code className="flex-1 text-sm bg-muted rounded-md px-3 py-2 overflow-x-auto uppercase">{stats.code}</code>
          <Button size="sm" variant="outline" onClick={() => copy(stats.code, "code")}>
            <Copy className="w-3.5 h-3.5 mr-1" /> {copied === "code" ? "Copiado!" : "Copiar"}
          </Button>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6 text-center">
            <TrendingUp className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">{stats.clicks}</div>
            <div className="text-xs text-muted-foreground">Cliques</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <Users className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">{stats.signups}</div>
            <div className="text-xs text-muted-foreground">Cadastros</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <ShoppingCart className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">{stats.buyers}</div>
            <div className="text-xs text-muted-foreground">Compradores</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6 text-center">
            <DollarSign className="w-5 h-5 mx-auto text-muted-foreground mb-1" />
            <div className="text-2xl font-bold">R$ {Number(stats.revenue_brl).toFixed(0)}</div>
            <div className="text-xs text-muted-foreground">Faturamento gerado</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão devida (a receber no fim do mês)</div>
            <div className="text-2xl font-bold text-amber-500">R$ {Number(stats.commission_due_brl).toFixed(2)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão já paga</div>
            <div className="text-2xl font-bold text-emerald-600">R$ {Number(stats.commission_paid_brl).toFixed(2)}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Uso ao longo do tempo</CardTitle>
          <div className="flex gap-1">
            <Button size="sm" variant={granularity === "day" ? "default" : "outline"} onClick={() => setGranularity("day")}>Dia</Button>
            <Button size="sm" variant={granularity === "month" ? "default" : "outline"} onClick={() => setGranularity("month")}>Mês</Button>
          </div>
        </CardHeader>
        <CardContent>
          {ts ? <TimeseriesChart ts={ts} /> : <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg flex items-center gap-2"><Ticket className="w-4 h-4" /> Cupom promocional</CardTitle>
          <Button size="sm" disabled={!!pendingCoupon} onClick={() => setShowCouponModal(true)}>
            {pendingCoupon ? "Aguardando análise" : "Solicitar cupom promocional"}
          </Button>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground mb-3">
            Além do seu cupom de convite (1ª compra), você pode solicitar um cupom promocional reutilizável,
            com prazo ou teto de faturamento definido pela administração. Só uma solicitação por vez.
          </p>
          {couponReqs === null ? (
            <div className="flex justify-center py-4"><Loader2 className="w-4 h-4 animate-spin text-muted-foreground" /></div>
          ) : couponReqs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma solicitação ainda.</p>
          ) : (
            <div className="space-y-2">
              {couponReqs.map((r) => (
                <div key={r.id} className="flex items-center justify-between text-sm border rounded-md px-3 py-2">
                  <div>
                    <span className="font-mono uppercase font-semibold">{r.coupon_code || r.requested_code}</span>
                    <span className="text-muted-foreground"> · {Number(r.discount_pct)}% desconto</span>
                    {r.status === "rejected" && r.rejection_reason && (
                      <div className="text-xs text-red-600 mt-0.5">Motivo: {r.rejection_reason}</div>
                    )}
                    {r.status === "approved" && r.limit_type === "days" && (
                      <div className="text-xs text-muted-foreground mt-0.5">Válido por {r.limit_days} dias</div>
                    )}
                    {r.status === "approved" && r.limit_type === "revenue" && (
                      <div className="text-xs text-muted-foreground mt-0.5">Até R$ {Number(r.limit_revenue_brl).toFixed(2)} de faturamento</div>
                    )}
                  </div>
                  <span className={
                    r.status === "approved" ? "text-emerald-600 text-xs font-semibold"
                      : r.status === "rejected" ? "text-red-600 text-xs font-semibold"
                        : "text-amber-500 text-xs font-semibold"
                  }>
                    {r.status === "approved" ? "Aprovado" : r.status === "rejected" ? "Recusado" : "Pendente"}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {referred && referred.items.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2"><UserPlus className="w-4 h-4" /> Parceiros indicados</CardTitle>
            <p className="text-xs text-muted-foreground">
              Override a receber: <span className="text-emerald-600 font-semibold">R$ {Number(referred.total_override_due_brl).toFixed(2)}</span> ({Number(referred.override_pct)}% da comissão de cada indicado)
            </p>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {referred.items.map((p) => (
                <div key={p.id} className="flex items-center justify-between text-sm border rounded-md px-3 py-2">
                  <div>
                    <span className="font-semibold">{p.name}</span>
                    <span className="text-muted-foreground"> · {p.users_count} compradores · R$ {Number(p.revenue_brl).toFixed(2)} gerados</span>
                  </div>
                  <span className="text-emerald-600 text-xs font-semibold">+R$ {Number(p.override_due_brl).toFixed(2)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {showCouponModal && (
        <CouponRequestModal
          onClose={() => setShowCouponModal(false)}
          onCreated={() => { setShowCouponModal(false); reloadCouponReqs(); }}
        />
      )}
    </div>
  );
}

function CouponRequestModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [code, setCode] = useState("");
  const [pct, setPct] = useState(10);
  const [msg, setMsg] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit() {
    setMsg(null);
    setSubmitting(true);
    try {
      await affiliatesApi.createCouponRequest(code.trim().toUpperCase(), pct);
      onCreated();
    } catch (e) {
      setMsg((e as Error).message || "Erro ao solicitar.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Solicitar cupom promocional</CardTitle>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="w-4 h-4" /></button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium">Nome do cupom (até 12 caracteres)</label>
            <input
              value={code} maxLength={12}
              onChange={(e) => setCode(e.target.value.replace(/[^a-zA-Z0-9]/g, "").toUpperCase())}
              className="mt-1 w-full rounded-md border bg-background px-3 py-2 text-sm font-mono uppercase"
              placeholder="EX: VERAO2026"
            />
          </div>
          <div>
            <label className="text-sm font-medium">Desconto ao usuário: {pct}% · sua comissão: {30 - pct}%</label>
            <input
              type="range" min={1} max={29} value={pct}
              onChange={(e) => setPct(Number(e.target.value))}
              className="mt-2 w-full"
            />
            <p className="text-xs text-muted-foreground mt-1">Orçamento de 30 pontos: desconto + comissão = 30%.</p>
          </div>
          {msg && <p className="text-sm text-red-600">{msg}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>Cancelar</Button>
            <Button disabled={submitting || code.length < 1} onClick={submit}>
              {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Enviar solicitação"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
