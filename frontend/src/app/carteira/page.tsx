"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
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

function getPackageBgImage(name: string, id: string): string {
  const n = (name || id || '').toLowerCase();
  if (n.includes('inicial')) return '/images/pacote-inicial.png';
  if (n.includes('essencial')) return '/images/pacote-essencial.png';
  if (n.includes('premium')) return '/images/pacote-premium.png';
  if (n.includes('ultimate')) return '/images/pacote-ultimate.png';
  return '/images/pacote-inicial.png';
}

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

  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

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
    let tries = 0;
    const id = setInterval(async () => {
      tries += 1;
      await refreshWallet();
      await load();
      if (tries >= 6) clearInterval(id);
    }, 5000);
    return () => clearInterval(id);
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
  const promo = wallet ? Number(wallet.promo_balance || 0) : 0;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <WalletIcon className="w-6 h-6 text-emerald-400" />
        <h1 className="text-2xl font-bold">Carteira</h1>
      </div>

      {/* Resumo da carteira */}
      <div className={`grid gap-4 ${promo > 0 ? "grid-cols-2 md:grid-cols-3" : "grid-cols-2"}`}>
        <Card className="border-border/60 bg-card/80 backdrop-blur-md">
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Créditos disponíveis</div>
            <div className="text-3xl font-bold flex items-center gap-2 mt-1 font-mono">
              <Coins className="w-6 h-6 text-emerald-400" /> {Math.floor(available)}
            </div>
          </CardContent>
        </Card>
        {promo > 0 && (
          <Card className="border-sky-500/30 bg-sky-500/[0.03] backdrop-blur-md">
            <CardContent className="pt-6">
              <div className="text-sm text-muted-foreground flex items-center gap-1">
                Promocionais
                <span title="Consumidos automaticamente em qualquer análise." className="cursor-help text-sky-500">ⓘ</span>
              </div>
              <div className="text-3xl font-bold mt-1 text-sky-400 font-mono">{Math.floor(promo)}</div>
            </CardContent>
          </Card>
        )}
        <Card className="cursor-pointer hover:border-amber-500/50 hover:bg-amber-500/[0.02] transition-all select-none group border-border/60 bg-card/80 backdrop-blur-md" onClick={() => router.push('/perfil?tab=selecoes')}>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground flex items-center justify-between">
              <span>Reservados</span>
              <span className="text-[10px] text-amber-400 font-semibold uppercase tracking-wider group-hover:translate-x-1 transition-transform">Ver seleções ➜</span>
            </div>
            <div className="text-3xl font-bold mt-1 text-amber-400 font-mono">{Math.floor(reserved)}</div>
          </CardContent>
        </Card>
      </div>

      {/* Campanha ativa */}
      {campaign?.banner && (
        <div className="rounded-2xl bg-gradient-to-r from-violet-700 to-violet-500 text-white p-4 flex items-center gap-3 shadow-lg">
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
        <div key={b.id} className="rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-500 text-white p-4 flex items-center gap-3 shadow-lg">
          <Sparkles className="w-5 h-5 shrink-0" />
          <div>
            <div className="font-semibold">{b.title}</div>
            {b.body && <div className="text-sm text-emerald-50">{b.body}</div>}
          </div>
        </div>
      ))}

      {msg && <div className="text-sm rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 p-3">{msg}</div>}
      {err && <div className="text-sm rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 p-3">{err}</div>}

      {/* Pacotes de créditos com imagem de fundo, filtro preto e branco no light mode e alta performance */}
      <div className="flex flex-col items-center justify-center pt-6 pb-2">
        <h2 className="text-2xl font-black tracking-widest bg-gradient-to-r from-emerald-400 via-cyan-400 to-indigo-400 bg-clip-text text-transparent uppercase">
          ESCOLHA SUA PROMOÇÃO:
        </h2>
        <div className="h-1 w-16 bg-gradient-to-r from-emerald-500 to-cyan-500 rounded-full mt-1.5 mb-2" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {packages.map((p) => {
          const badge = p.featured_badge ? BADGE_LABEL[p.featured_badge] : null;
          const isRecommended = !badge && p.id === recommendedId;
          const pct = savingsPct(p);
          const cleanName = p.name.replace(/pacote\s*/i, "");
          const bgImg = getPackageBgImage(p.name, p.id);

          return (
            <div
              key={p.id}
              className={`group relative rounded-2xl border p-5 flex flex-col items-center text-center justify-between gap-3 transition-all duration-300 hover:-translate-y-1.5 hover:shadow-2xl select-none overflow-hidden cursor-pointer bg-card/85 backdrop-blur-xl border-border/60 ${
                badge
                  ? "hover:border-emerald-500/70 hover:shadow-emerald-500/20"
                  : isRecommended
                  ? "hover:border-violet-500/70 hover:shadow-violet-500/20"
                  : "hover:border-emerald-500/50 hover:shadow-emerald-500/10"
              }`}
            >
              {/* Imagem de Fundo com Alta Nitidez e filtro Grayscale no modo claro */}
              <div className="absolute inset-0 pointer-events-none overflow-hidden z-0">
                <img
                  src={bgImg}
                  alt=""
                  className="w-full h-full object-cover blur-[2px] scale-105 opacity-70 dark:opacity-65 dark:grayscale-0 grayscale contrast-110 brightness-105 transition-transform duration-500 group-hover:scale-110"
                  loading="eager"
                />
                <div className="absolute inset-0 bg-gradient-to-b from-card/40 via-card/65 to-card/85" />
              </div>

              {badge && (
                <span className={`absolute top-2 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full whitespace-nowrap shadow-md z-10 ${badge.className}`}>
                  {badge.label}
                </span>
              )}
              {isRecommended && (
                <span className="absolute top-2 left-1/2 -translate-x-1/2 text-[10px] font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full whitespace-nowrap bg-primary text-primary-foreground shadow-md z-10">
                  Recomendado
                </span>
              )}

              <div className="relative z-10 w-full flex flex-col items-center pt-2">
                <div className="text-xs uppercase tracking-wider text-muted-foreground font-bold">{cleanName}</div>
                <div className="text-4xl font-black font-mono tracking-tight text-foreground my-1">{p.total_credits}</div>
                <div className="text-[11px] text-muted-foreground font-medium">créditos{p.bonus_credits ? ` (+${p.bonus_credits} bônus)` : ""}</div>
              </div>

              <div className="relative z-10 w-full flex flex-col items-center space-y-1 my-2">
                <div className="text-lg font-extrabold text-foreground font-mono">R$ {Number(p.price_brl).toFixed(2)}</div>
                <div className="text-[10.5px] text-muted-foreground font-mono">R$ {pricePerCredit(p).toFixed(2)} / crédito</div>
                {pct > 0 && <div className="text-[11px] font-bold text-emerald-400 font-mono">Economize {pct}%</div>}
              </div>

              <Button size="sm" className="relative z-10 w-full bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-600 hover:to-cyan-600 border-0 text-white font-bold shadow-md shadow-emerald-500/20 active:scale-95 transition-all" onClick={() => startBuy(p)}>
                <Plus className="w-3.5 h-3.5 mr-1" /> Adquirir
              </Button>
            </div>
          );
        })}
      </div>

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
          ) : (() => {
            const totalPages = Math.ceil(txs.length / itemsPerPage);
            const start = (currentPage - 1) * itemsPerPage;
            const paginatedTxs = txs.slice(start, start + itemsPerPage);
            return (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground border-b border-border/50">
                        <th className="py-2 px-3 font-semibold">Data / Hora</th>
                        <th className="py-2 px-3 font-semibold">Operação</th>
                        <th className="py-2 px-3 font-semibold">Detalhes</th>
                        <th className="py-2 px-3 font-semibold text-center">Créditos</th>
                        <th className="py-2 px-3 font-semibold text-right">Saldo</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedTxs.map((t) => {
                        const isCredit = Number(t.amount) >= 0;
                        const matchLabel = t.home_team && t.away_team ? `${teamPt(t.home_team)} × ${teamPt(t.away_team)}` : null;
                        return (
                          <tr key={t.id} className="border-b border-border/30 last:border-0 hover:bg-muted/30 transition-colors">
                            <td className="py-3 px-3 text-xs text-muted-foreground whitespace-nowrap">
                              {new Date(t.created_at).toLocaleString("pt-BR")}
                            </td>
                            <td className="py-3 px-3">
                              <div className="font-medium flex items-center gap-1.5 flex-wrap">
                                <span>{TX_LABEL[t.type] || t.type}</span>
                                <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${t.status === "completed" ? "bg-emerald-500/10 text-emerald-600" : t.status === "reversed" ? "bg-red-500/10 text-red-600" : "bg-amber-500/10 text-amber-600"}`}>
                                  {t.status === "completed" ? "Concluído" : t.status === "reversed" ? "Estornado" : "Pendente"}
                                </span>
                              </div>
                            </td>
                            <td className="py-3 px-3 text-xs text-muted-foreground">
                              {matchLabel ? matchLabel : (t.description || "—")}
                            </td>
                            <td className={`py-3 px-3 text-center font-mono font-bold ${isCredit ? "text-emerald-500" : "text-red-500"}`}>
                              {isCredit ? "+" : ""}{Number(t.amount).toFixed(0)}
                            </td>
                            <td className="py-3 px-3 text-right">
                              <span className="font-mono text-foreground font-medium">{Number(t.balance_after).toFixed(0)}</span>
                              {Number(t.reserved_after) > 0 && (
                                <span className="text-[10px] text-muted-foreground block">
                                  (+{Number(t.reserved_after).toFixed(0)} reservado)
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {totalPages > 1 && (
                  <div className="flex items-center justify-between mt-4 pt-2 border-t border-border/50 text-xs">
                    <span className="text-muted-foreground">
                      Página <strong>{currentPage}</strong> de {totalPages} ({txs.length} registros)
                    </span>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={currentPage === 1}
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        className="h-7 text-[11px]"
                      >
                        Anterior
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={currentPage === totalPages}
                        onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                        className="h-7 text-[11px]"
                      >
                        Próximo
                      </Button>
                    </div>
                  </div>
                )}
              </>
            );
          })()}
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
