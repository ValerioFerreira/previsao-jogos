"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Coins, Loader2, Plus, Sparkles, Tag, Wallet as WalletIcon } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import {
  paymentsApi, walletApiFull, promotionsApi, bannersApi, ordersApi,
  type CreditPackage, type Transaction, type CouponPreview, type Banner, type OrderListItem,
} from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const TX_LABEL: Record<string, string> = {
  purchase: "Compra de créditos",
  bonus: "Bônus",
  promo_credit: "Crédito promocional",
  reservation: "Reserva (análise futura)",
  reservation_release: "Estorno de reserva",
  consumption: "Consumo",
  refund: "Estorno",
  chargeback: "Estorno (chargeback)",
  manual_adjustment: "Ajuste manual",
  cashback: "Cashback",
};

const BADGE_LABEL: Record<string, { label: string; className: string }> = {
  mais_vendido: { label: "★ Mais vendido", className: "bg-amber-500 text-white" },
  melhor_oferta: { label: "Melhor custo-benefício", className: "bg-emerald-600 text-white" },
  oferta_limitada: { label: "Oferta por tempo limitado", className: "bg-rose-600 text-white" },
};

export default function CarteiraPage() {
  const { user, wallet, loading, refreshWallet } = useAuth();
  const router = useRouter();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [banners, setBanners] = useState<Banner[]>([]);
  const [pendingOrders, setPendingOrders] = useState<OrderListItem[]>([]);
  const [recommendedId, setRecommendedId] = useState<string | null>(null);
  const [myOrders, setMyOrders] = useState<OrderListItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const [couponCode, setCouponCode] = useState("");
  const [couponPreview, setCouponPreview] = useState<CouponPreview | null>(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [couponErr, setCouponErr] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  const load = useCallback(async () => {
    try {
      const [pk, tx, bn, pend, mine, rec] = await Promise.all([
        paymentsApi.packages(), walletApiFull.transactions(50),
        bannersApi.active().catch(() => ({ items: [] })),
        ordersApi.pending().catch(() => []),
        ordersApi.mine().catch(() => []),
        paymentsApi.recommended().catch(() => null),
      ]);
      setPackages([...pk].sort((a, b) => (a.credits + a.bonus_credits) - (b.credits + b.bonus_credits)));
      setTxs(tx.items);
      setBanners(bn.items);
      setPendingOrders(pend);
      setMyOrders(mine);
      setRecommendedId(rec?.id ?? null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const status = params.get("status");
    if (!status) return;
    if (status === "success") setMsg("Pagamento em confirmação — os créditos aparecem assim que o provedor confirmar (normalmente poucos segundos).");
    else if (status === "pending") setMsg("Pagamento pendente (ex.: Pix aguardando compensação). Os créditos são liberados automaticamente após a confirmação.");
    else if (status === "failure") setErr("Pagamento não concluído. Você pode tentar novamente.");
    window.history.replaceState({}, "", "/carteira");
    // poll rápido para refletir o crédito assim que o webhook processar
    let tries = 0;
    const id = setInterval(async () => {
      tries += 1;
      await refreshWallet();
      await load();
      if (tries >= 6) clearInterval(id);
    }, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function pricePerCredit(p: CreditPackage) {
    const total = p.total_credits || (p.credits + p.bonus_credits);
    return total > 0 ? Number(p.price_brl) / total : 0;
  }

  function savingsPct(p: CreditPackage) {
    if (!p.bonus_credits) return 0;
    const total = p.credits + p.bonus_credits;
    return Math.round((p.bonus_credits / total) * 100);
  }

  async function applyCoupon() {
    if (!couponCode.trim()) return;
    setCouponBusy(true);
    setCouponErr(null);
    setCouponPreview(null);
    try {
      // usa o pacote de referência apenas p/ preview de valor mínimo/pacote-específico;
      // a validação de verdade (server-side) roda de novo no checkout.
      const ref = packages[packages.length - 1];
      const preview = await promotionsApi.validateCoupon({
        code: couponCode.trim(), amount_brl: ref ? ref.price_brl : "0", credits: ref ? ref.total_credits : 0,
      });
      setCouponPreview(preview);
    } catch (e) {
      setCouponErr((e as Error).message);
    } finally {
      setCouponBusy(false);
    }
  }

  async function buy(pkg: CreditPackage) {
    setBusyId(pkg.id);
    setErr(null);
    setMsg(null);
    try {
      const order = await paymentsApi.checkout({
        package_id: pkg.id,
        coupon_code: couponPreview ? couponCode.trim() : undefined,
      });
      if (order.provider === "mock") {
        // gateway MOCK: confirma o pagamento imediatamente (dev/sandbox local)
        await paymentsApi.mockConfirm(order.order_id);
        await refreshWallet();
        await load();
        setMsg(`Compra confirmada: +${order.credits} créditos.`);
      } else {
        // gateway real: o crédito só é liberado pelo webhook do provedor, nunca pelo
        // cliente — redireciona para o checkout hospedado e o usuário volta com
        // ?status=success|pending|failure.
        const initPoint = (order.checkout?.init_point as string | undefined)
          || (order.checkout?.sandbox_init_point as string | undefined);
        if (!initPoint) throw new Error("Checkout indisponível — tente novamente em instantes.");
        window.location.href = initPoint;
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  function reopenCheckout(o: OrderListItem) {
    const initPoint = (o.checkout?.init_point as string | undefined) || (o.checkout?.sandbox_init_point as string | undefined);
    if (initPoint) window.location.href = initPoint;
  }

  if (loading || !user) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  const available = wallet ? Number(wallet.available_balance) : 0;
  const reserved = wallet ? Number(wallet.reserved_balance) : 0;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <WalletIcon className="w-6 h-6" />
        <h1 className="text-2xl font-bold">Carteira</h1>
      </div>

      {/* 1. Banner promocional */}
      {banners.map((b) => (
        <div key={b.id} className="rounded-lg bg-gradient-to-r from-emerald-600 to-emerald-500 text-white p-4 flex items-center gap-3">
          <Sparkles className="w-5 h-5 shrink-0" />
          <div>
            <div className="font-semibold">{b.title}</div>
            {b.body && <div className="text-sm text-emerald-50">{b.body}</div>}
          </div>
        </div>
      ))}

      {msg && <div className="text-sm rounded-md bg-emerald-500/10 text-emerald-600 p-3">{msg}</div>}
      {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      {/* 2/3. Pacotes de créditos (com selos de destaque) */}
      <Card>
        <CardHeader><CardTitle className="text-lg">Comprar créditos</CardTitle></CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground mb-4">
            Cada crédito custa R$ 1,00 e remunera o uso da Inteligência Artificial.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {packages.map((p) => {
              const badge = p.featured_badge ? BADGE_LABEL[p.featured_badge] : null;
              const isRecommended = !badge && p.id === recommendedId;
              const pct = savingsPct(p);
              return (
                <div key={p.id} className={`relative rounded-lg border p-4 flex flex-col items-center text-center gap-2 ${badge ? "border-emerald-500 shadow-md" : isRecommended ? "border-primary shadow-sm" : ""}`}>
                  {badge && (
                    <span className={`absolute -top-2.5 left-1/2 -translate-x-1/2 text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap ${badge.className}`}>
                      {badge.label}
                    </span>
                  )}
                  {isRecommended && (
                    <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 text-[10px] font-semibold px-2 py-0.5 rounded-full whitespace-nowrap bg-primary text-primary-foreground">
                      Recomendado para você
                    </span>
                  )}
                  <div className="text-2xl font-bold mt-2">{p.total_credits}</div>
                  <div className="text-xs text-muted-foreground">créditos{p.bonus_credits ? ` (+${p.bonus_credits} bônus)` : ""}</div>
                  <div className="text-sm font-semibold">R$ {Number(p.price_brl).toFixed(2)}</div>
                  <div className="text-[11px] text-muted-foreground">R$ {pricePerCredit(p).toFixed(2)} por crédito</div>
                  {pct > 0 && <div className="text-[11px] font-medium text-emerald-600">Economize {pct}%</div>}
                  <Button size="sm" className="w-full mt-1" disabled={busyId === p.id} onClick={() => buy(p)}>
                    {busyId === p.id ? <Loader2 className="w-4 h-4 animate-spin" /> : (<><Plus className="w-3.5 h-3.5 mr-1" /> Comprar</>)}
                  </Button>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* 4. Código promocional */}
      <Card>
        <CardHeader><CardTitle className="text-lg flex items-center gap-2"><Tag className="w-4 h-4" /> Código promocional</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <div className="flex gap-2">
            <Input placeholder="Código promocional" value={couponCode}
                  onChange={(e) => { setCouponCode(e.target.value.toUpperCase()); setCouponPreview(null); setCouponErr(null); }} />
            <Button variant="outline" disabled={couponBusy || !couponCode.trim()} onClick={applyCoupon}>
              {couponBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Aplicar"}
            </Button>
          </div>
          {couponErr && <p className="text-xs text-red-600">{couponErr}</p>}
          {couponPreview && (
            <div className="text-sm rounded-md bg-emerald-500/10 text-emerald-700 p-2.5">
              Cupom aplicado — {couponPreview.bonus_credits > 0
                ? `+${couponPreview.bonus_credits} créditos bônus`
                : `de R$ ${Number(couponPreview.original_amount_brl).toFixed(2)} por R$ ${Number(couponPreview.final_amount_brl).toFixed(2)}`}.
              Válido na próxima compra abaixo.
            </div>
          )}
        </CardContent>
      </Card>

      {/* 6. Pagamentos pendentes (recuperação de PIX) */}
      {pendingOrders.length > 0 && (
        <Card className="border-amber-500">
          <CardContent className="pt-6 space-y-3">
            {pendingOrders.map((o) => (
              <div key={o.order_id} className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-sm">
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                  <span>Você possui um pagamento pendente de R$ {Number(o.amount_brl).toFixed(2)} ({o.credits} créditos). Deseja continuar?</span>
                </div>
                <Button size="sm" variant="outline" onClick={() => reopenCheckout(o)}>Continuar pagamento</Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* 5. Resumo da carteira */}
      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Créditos disponíveis</div>
            <div className="text-3xl font-bold flex items-center gap-2 mt-1">
              <Coins className="w-6 h-6 text-emerald-500" /> {Math.floor(available)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Reservados</div>
            <div className="text-3xl font-bold mt-1 text-amber-500">{Math.floor(reserved)}</div>
          </CardContent>
        </Card>
      </div>

      {/* 7. Histórico financeiro */}
      <Card>
        <CardHeader><CardTitle className="text-lg">Histórico financeiro</CardTitle></CardHeader>
        <CardContent>
          {txs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma movimentação ainda.</p>
          ) : (
            <div className="divide-y">
              {txs.map((t) => (
                <div key={t.id} className="flex items-center justify-between py-2.5 text-sm">
                  <div>
                    <div className="font-medium">{TX_LABEL[t.type] || t.type}</div>
                    <div className="text-xs text-muted-foreground">
                      {new Date(t.created_at).toLocaleString("pt-BR")}
                      {t.description ? ` · ${t.description}` : ""}
                    </div>
                  </div>
                  <div className={`font-mono font-semibold ${Number(t.amount) >= 0 ? "text-emerald-600" : "text-red-600"}`}>
                    {Number(t.amount) >= 0 ? "+" : ""}{Number(t.amount).toFixed(0)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 8. Minhas compras */}
      <Card>
        <CardHeader><CardTitle className="text-lg">Minhas compras</CardTitle></CardHeader>
        <CardContent>
          {myOrders.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma compra ainda.</p>
          ) : (
            <div className="divide-y">
              {myOrders.map((o) => (
                <div key={o.order_id} className="flex items-center justify-between py-2.5 text-sm">
                  <div>
                    <div className="font-medium">{o.credits} créditos · R$ {Number(o.amount_brl).toFixed(2)}</div>
                    <div className="text-xs text-muted-foreground">
                      {new Date(o.created_at).toLocaleString("pt-BR")} · {o.provider}
                      {o.method ? ` · ${o.method}` : ""}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {o.invoice_url && <a href={o.invoice_url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">Nota fiscal</a>}
                    <span className={`text-xs px-2 py-0.5 rounded ${o.status === "paid" ? "bg-emerald-500/10 text-emerald-600" : o.status === "pending" ? "bg-amber-500/10 text-amber-600" : "bg-muted text-muted-foreground"}`}>
                      {o.status === "paid" ? "Pago" : o.status === "pending" ? "Pendente" : o.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
