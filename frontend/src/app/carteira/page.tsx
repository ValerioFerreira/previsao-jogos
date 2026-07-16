"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  AlertTriangle, Coins, Copy, FileCheck2, Gift, Loader2, Plus, Receipt, Share2, ShoppingBag,
  Sparkles, Wallet as WalletIcon, X,
} from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi, type ReferralInfo } from "@/lib/authApi";
import {
  paymentsApi, walletApiFull, bannersApi, ordersApi, campaignsApi, legalApi,
  type CreditPackage, type Transaction, type Banner, type OrderListItem, type ActiveCampaign, type LegalDoc,
} from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CheckoutModal } from "@/components/platform/CheckoutModal";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { teamPt } from "@/lib/teamNames";

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
  melhor_para_comecar: { label: "Melhor para começar", className: "bg-sky-600 text-white" },
  melhor_custo_beneficio: { label: "💎 Melhor custo-benefício", className: "bg-violet-600 text-white" },
};

export default function CarteiraPage() {
  const { user, wallet, loading, refreshWallet } = useAuth();
  const router = useRouter();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [banners, setBanners] = useState<Banner[]>([]);
  const [campaign, setCampaign] = useState<ActiveCampaign | null>(null);
  const [referral, setReferral] = useState<ReferralInfo | null>(null);
  const [pendingOrders, setPendingOrders] = useState<OrderListItem[]>([]);
  const [recommendedId, setRecommendedId] = useState<string | null>(null);
  const [myOrders, setMyOrders] = useState<OrderListItem[]>([]);
  const [pendingDocs, setPendingDocs] = useState<LegalDoc[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [checkoutPkg, setCheckoutPkg] = useState<CreditPackage | null>(null);
  const [legalGateOpen, setLegalGateOpen] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [invoiceModalOrder, setInvoiceModalOrder] = useState<OrderListItem | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  const load = useCallback(async () => {
    try {
      const [pk, tx, bn, camp, ref, pend, mine, rec, pendingLegal] = await Promise.all([
        paymentsApi.packages(), walletApiFull.transactions(50),
        bannersApi.active().catch(() => ({ items: [] })),
        campaignsApi.active().catch(() => ({ items: [] })),
        authApi.myReferral().catch(() => null),
        ordersApi.pending().catch(() => []),
        ordersApi.mine().catch(() => []),
        paymentsApi.recommended().catch(() => null),
        legalApi.pending().catch(() => []),
      ]);
      setPackages([...pk].sort((a, b) => (a.credits + a.bonus_credits) - (b.credits + b.bonus_credits)));
      setTxs(tx.items);
      setBanners(bn.items);
      setCampaign(camp.items[0] ?? null);
      setReferral(ref);
      setPendingOrders(pend);
      setMyOrders(mine);
      setRecommendedId(rec?.id ?? null);
      setPendingDocs(pendingLegal);
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

  function startBuy(pkg: CreditPackage) {
    setErr(null);
    setMsg(null);
    if (pendingDocs.length > 0) {
      setLegalGateOpen(true);
      return;
    }
    setCheckoutPkg(pkg);
  }

  async function onConfirmed(result: { credits: number }) {
    await refreshWallet();
    await load();
    setMsg(`Compra confirmada: +${result.credits} créditos.`);
  }

  function reopenCheckout(o: OrderListItem) {
    const initPoint = (o.checkout?.init_point as string | undefined) || (o.checkout?.sandbox_init_point as string | undefined);
    if (initPoint) window.location.href = initPoint;
  }

  async function cancelOrder(o: OrderListItem) {
    setBusyId(o.order_id);
    setErr(null);
    try {
      await ordersApi.cancel(o.order_id);
      setPendingOrders((prev) => prev.filter((x) => x.order_id !== o.order_id));
      await load();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function confirmInvoice(o: OrderListItem) {
    setBusyId(o.order_id);
    setErr(null);
    try {
      const updated = await ordersApi.requestInvoice(o.order_id);
      setMyOrders((prev) => prev.map((x) => (x.order_id === updated.order_id ? updated : x)));
      setInvoiceModalOrder(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusyId(null);
    }
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

      {/* Resumo da carteira — primeiro, antes de vendas/banners */}
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

      {/* Campanha ativa (prioridade máxima) — banner amarra cupom/pacotes participantes */}
      {campaign?.banner && (
        <div className="rounded-lg bg-gradient-to-r from-violet-700 to-violet-500 text-white p-4 flex items-center gap-3">
          <Sparkles className="w-5 h-5 shrink-0" />
          <div>
            <div className="font-semibold">{campaign.banner.title}</div>
            {campaign.banner.body && <div className="text-sm text-violet-50">{campaign.banner.body}</div>}
            {campaign.coupons.length > 0 && (
              <div className="text-xs text-violet-100 mt-1">
                Use o cupom <span className="font-mono font-semibold">{campaign.coupons[0].code}</span> no checkout.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Banners promocionais */}
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

      {/* Pacotes de créditos (com selos de destaque) */}
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
                  <div className="text-sm font-semibold mt-2">{p.name}</div>
                  <div className="text-2xl font-bold">{p.total_credits}</div>
                  <div className="text-xs text-muted-foreground">créditos{p.bonus_credits ? ` (+${p.bonus_credits} bônus)` : ""}</div>
                  <div className="text-sm font-semibold">R$ {Number(p.price_brl).toFixed(2)}</div>
                  <div className="text-[11px] text-muted-foreground">R$ {pricePerCredit(p).toFixed(2)} por crédito</div>
                  {pct > 0 && <div className="text-[11px] font-medium text-emerald-600">Economize {pct}%</div>}
                  <Button size="sm" className="w-full mt-1" onClick={() => startBuy(p)}>
                    <Plus className="w-3.5 h-3.5 mr-1" /> Comprar
                  </Button>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Convide seus amigos (indicação — independente do programa de afiliados) */}
      {referral?.referral_code && (
        <Card>
          <CardHeader><CardTitle className="text-lg flex items-center gap-2"><Gift className="w-4 h-4" /> Convide seus amigos</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Você e seu amigo recebem créditos grátis quando ele usar seu código no cadastro.
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-lg font-bold px-3 py-1.5 rounded-md bg-muted">{referral.referral_code}</span>
              <Button size="sm" variant="outline" onClick={() => {
                navigator.clipboard.writeText(referral.referral_code || "");
                setCopied(true); setTimeout(() => setCopied(false), 2000);
              }}>
                <Copy className="w-3.5 h-3.5 mr-1" /> {copied ? "Copiado!" : "Copiar código"}
              </Button>
              {referral.share_link && (
                <Button size="sm" variant="outline" onClick={() => {
                  if (navigator.share) navigator.share({ url: referral.share_link! });
                  else { navigator.clipboard.writeText(referral.share_link!); setCopied(true); setTimeout(() => setCopied(false), 2000); }
                }}>
                  <Share2 className="w-3.5 h-3.5 mr-1" /> Compartilhar
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {referral.completed_referrals} indicação(ões) concluída(s) · {referral.credits_earned} créditos ganhos
            </p>
          </CardContent>
        </Card>
      )}

      {/* Pagamentos pendentes (recuperação de PIX) */}
      {pendingOrders.length > 0 && (
        <Card className="border-amber-500">
          <CardContent className="pt-6 space-y-3">
            {pendingOrders.map((o) => (
              <div key={o.order_id} className="flex items-center justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 text-sm">
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                  <span>Você possui um pagamento pendente de R$ {Number(o.amount_brl).toFixed(2)} ({o.credits} créditos). Deseja continuar?</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="ghost" disabled={busyId === o.order_id}
                          onClick={() => cancelOrder(o)}>
                    {busyId === o.order_id ? <Loader2 className="w-4 h-4 animate-spin" /> : <><X className="w-3.5 h-3.5 mr-1" /> Cancelar</>}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => reopenCheckout(o)}>Continuar pagamento</Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Histórico */}
      <Card>
        <CardHeader><CardTitle className="text-lg flex items-center gap-2"><Receipt className="w-4 h-4" /> Histórico</CardTitle></CardHeader>
        <CardContent>
          {txs.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma movimentação ainda.</p>
          ) : (
            <div className="space-y-2">
              {txs.map((t) => {
                const isCredit = Number(t.amount) >= 0;
                const matchLabel = t.home_team && t.away_team ? `${teamPt(t.home_team)} × ${teamPt(t.away_team)}` : null;
                return (
                  <div key={t.id} className="rounded-lg border border-border/50 p-3 flex items-center justify-between gap-3 flex-wrap">
                    <div className="min-w-0">
                      <div className="font-medium flex items-center gap-2">
                        {TX_LABEL[t.type] || t.type}
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${t.status === "completed" ? "bg-emerald-500/10 text-emerald-600" : t.status === "reversed" ? "bg-red-500/10 text-red-600" : "bg-amber-500/10 text-amber-600"}`}>
                          {t.status === "completed" ? "Concluído" : t.status === "reversed" ? "Estornado" : "Pendente"}
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        {new Date(t.created_at).toLocaleString("pt-BR")}
                        {matchLabel ? ` · ${matchLabel}` : (t.description ? ` · ${t.description}` : "")}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className={`font-mono font-semibold ${isCredit ? "text-emerald-600" : "text-red-600"}`}>
                        {isCredit ? "+" : ""}{Number(t.amount).toFixed(0)}
                      </div>
                      <div className="text-[11px] text-muted-foreground">saldo: {Number(t.balance_after).toFixed(0)}
                        {Number(t.reserved_after) > 0 ? ` (+${Number(t.reserved_after).toFixed(0)} reservado)` : ""}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Minhas compras */}
      <Card>
        <CardHeader><CardTitle className="text-lg flex items-center gap-2"><ShoppingBag className="w-4 h-4" /> Minhas compras</CardTitle></CardHeader>
        <CardContent>
          {myOrders.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhuma compra ainda.</p>
          ) : (
            <div className="space-y-2">
              {myOrders.map((o) => (
                <div key={o.order_id} className="rounded-lg border border-border/50 p-3 flex items-center justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className="font-medium">{o.credits} créditos · R$ {Number(o.amount_brl).toFixed(2)}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {new Date(o.created_at).toLocaleString("pt-BR")} · {o.provider}
                      {o.method ? ` · ${o.method}` : ""}
                      {o.coupon_code ? ` · cupom ${o.coupon_code}` : ""}
                      {o.discount_amount_brl && Number(o.discount_amount_brl) > 0 ? ` (−R$ ${Number(o.discount_amount_brl).toFixed(2)})` : ""}
                    </div>
                    {o.paid_at && (
                      <div className="text-[11px] text-muted-foreground mt-0.5">Pago em {new Date(o.paid_at).toLocaleString("pt-BR")}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {o.status === "paid" && !o.invoice_url && (
                      <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busyId === o.order_id}
                              onClick={() => setInvoiceModalOrder(o)}>
                        <FileCheck2 className="w-3.5 h-3.5 mr-1" /> Emitir nota fiscal
                      </Button>
                    )}
                    {o.invoice_url && (
                      <a href={o.invoice_url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">Ver nota fiscal</a>
                    )}
                    {o.invoice_requested_at && !o.invoice_url && (
                      <span className="text-xs text-muted-foreground">Nota fiscal em processamento</span>
                    )}
                    <span className={`text-xs px-2 py-0.5 rounded ${o.status === "paid" ? "bg-emerald-500/10 text-emerald-600" : o.status === "pending" ? "bg-amber-500/10 text-amber-600" : "bg-muted text-muted-foreground"}`}>
                      {o.status === "paid" ? "Pago" : o.status === "pending" ? "Pendente" : o.status === "canceled" ? "Cancelado" : o.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <CheckoutModal
        pkg={checkoutPkg}
        open={!!checkoutPkg}
        onOpenChange={(open) => { if (!open) setCheckoutPkg(null); }}
        onConfirmed={onConfirmed}
      />

      <Dialog open={legalGateOpen} onOpenChange={setLegalGateOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Documentos pendentes</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Antes de comprar créditos, você precisa ler e aceitar {pendingDocs.length === 1 ? "o documento pendente" : `os ${pendingDocs.length} documentos pendentes`} (Termos de Uso, Política de Privacidade e demais).
          </p>
          <Button className="w-full" onClick={() => router.push("/documentos")}>Ir para Documentos</Button>
        </DialogContent>
      </Dialog>

      <Dialog open={!!invoiceModalOrder} onOpenChange={(open) => { if (!open) setInvoiceModalOrder(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Emitir nota fiscal</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Você receberá a nota fiscal por e-mail assim que ela for emitida. Deseja continuar?
          </p>
          <div className="flex gap-2 justify-end">
            <Button variant="outline" onClick={() => setInvoiceModalOrder(null)} disabled={!!busyId}>Cancelar</Button>
            <Button onClick={() => invoiceModalOrder && confirmInvoice(invoiceModalOrder)} disabled={!!busyId}>
              {busyId === invoiceModalOrder?.order_id ? <Loader2 className="w-4 h-4 animate-spin" /> : "Confirmar"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
