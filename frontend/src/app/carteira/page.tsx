"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Coins, Loader2, Plus, Wallet as WalletIcon } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { paymentsApi, walletApiFull, type CreditPackage, type Transaction } from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

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

export default function CarteiraPage() {
  const { user, wallet, loading, refreshWallet } = useAuth();
  const router = useRouter();
  const [packages, setPackages] = useState<CreditPackage[]>([]);
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  const load = useCallback(async () => {
    try {
      const [pk, tx] = await Promise.all([paymentsApi.packages(), walletApiFull.transactions(50)]);
      setPackages(pk);
      setTxs(tx.items);
    } catch (e) {
      setErr((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (user) load();
  }, [user, load]);

  async function buy(pkg: CreditPackage) {
    setBusyId(pkg.id);
    setErr(null);
    setMsg(null);
    try {
      const order = await paymentsApi.checkout({ package_id: pkg.id });
      // gateway MOCK: confirma o pagamento imediatamente (dev)
      await paymentsApi.mockConfirm(order.order_id);
      await refreshWallet();
      await load();
      setMsg(`Compra confirmada: +${pkg.total_credits} créditos.`);
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

      {/* Saldos */}
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

      {msg && <div className="text-sm rounded-md bg-emerald-500/10 text-emerald-600 p-3">{msg}</div>}
      {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      {/* Comprar créditos */}
      <Card>
        <CardHeader><CardTitle className="text-lg">Comprar créditos</CardTitle></CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground mb-4">
            Cada crédito custa R$ 1,00 e remunera o uso da Inteligência Artificial. (Pagamento em modo demonstração.)
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {packages.map((p) => (
              <div key={p.id} className="rounded-lg border p-4 flex flex-col items-center text-center gap-2">
                <div className="text-2xl font-bold">{p.total_credits}</div>
                <div className="text-xs text-muted-foreground">créditos{p.bonus_credits ? ` (+${p.bonus_credits} bônus)` : ""}</div>
                <div className="text-sm font-semibold">R$ {Number(p.price_brl).toFixed(2)}</div>
                <Button size="sm" className="w-full mt-1" disabled={busyId === p.id} onClick={() => buy(p)}>
                  {busyId === p.id ? <Loader2 className="w-4 h-4 animate-spin" /> : (<><Plus className="w-3.5 h-3.5 mr-1" /> Comprar</>)}
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Extrato */}
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
    </div>
  );
}
