"use client";
import React, { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Loader2, ArrowRight, CheckCircle2 } from "lucide-react";
import { affiliatesApi } from "@/lib/affiliatesApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import InfoTooltip from "@/components/platform/InfoTooltip";

const DISCOUNT_TIERS = [5, 10, 15, 20, 25];
const COMMISSION_BUDGET_PCT = 30;

function commissionPer100(discountPct: number): string {
  const commissionRatePct = COMMISSION_BUDGET_PCT - discountPct;
  const paidPer100 = 100 - discountPct;
  return ((commissionRatePct * paidPer100) / 100).toFixed(2);
}

export default function SolicitarParceriaPage() {
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [form, setForm] = useState({ full_name: "", email: "", cpf: "", phone: "" });
  const [paymentType, setPaymentType] = useState<"pf" | "pj">("pf");
  const [discountPct, setDiscountPct] = useState(15);

  const upd = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await affiliatesApi.apply({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        cpf: form.cpf.replace(/\D/g, ""),
        phone: form.phone.replace(/\D/g, ""),
        payment_type: paymentType,
        discount_pct: discountPct,
      });
      setDone(true);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="max-w-md mx-auto mt-6 sm:mt-12">
        <Card>
          <CardContent className="pt-8 pb-8 text-center space-y-3">
            <CheckCircle2 className="w-10 h-10 mx-auto text-emerald-500" />
            <h1 className="text-xl font-bold">Solicitação enviada!</h1>
            <p className="text-sm text-muted-foreground">
              Vamos analisar seu pedido e entrar em contato em breve. Assim que aprovado, você
              recebe um e-mail com o link para definir sua senha e acessar o portal do parceiro.
            </p>
            <Link href="/" className="inline-block text-sm text-primary hover:underline">Voltar para a página inicial</Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto mt-6 sm:mt-12 mb-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Seja um Parceiro</CardTitle>
          <CardDescription>
            Divulgue o ApostAI com seu próprio código de desconto e ganhe comissão por venda.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {err && <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="nome">Nome completo</Label>
              <Input id="nome" value={form.full_name} onChange={upd("full_name")} placeholder="Maria da Silva" required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" value={form.email} onChange={upd("email")} placeholder="voce@email.com" required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="cpf">CPF</Label>
                <Input id="cpf" value={form.cpf} onChange={upd("cpf")} placeholder="000.000.000-00" required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tel">Telefone (WhatsApp)</Label>
                <Input id="tel" value={form.phone} onChange={upd("phone")} placeholder="(11) 90000-0000" required />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="flex items-center">
                Forma de pagamento
                <InfoTooltip text="É a forma como o site vai remunerar você pelas vendas com o seu código — combinamos os detalhes de pagamento diretamente com você após a aprovação." />
              </Label>
              <Select value={paymentType} onValueChange={(v) => setPaymentType(v as "pf" | "pj")}>
                <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="pf">Pessoa física (PF)</SelectItem>
                  <SelectItem value="pj">Pessoa jurídica (PJ)</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label className="flex items-center">
                Desconto que você quer oferecer
                <InfoTooltip text="Você escolhe o desconto dado ao usuário; o restante de um orçamento de 30 pontos percentuais vira sua comissão sobre o valor pago. Quanto menor o desconto, maior sua comissão." />
              </Label>
              <div className="grid grid-cols-5 gap-1.5">
                {DISCOUNT_TIERS.map((tier) => (
                  <button
                    key={tier}
                    type="button"
                    onClick={() => setDiscountPct(tier)}
                    className={`py-2 text-sm font-semibold rounded-md border transition-colors ${
                      discountPct === tier
                        ? "bg-primary text-primary-foreground border-primary"
                        : "bg-muted text-muted-foreground border-transparent hover:text-foreground"
                    }`}
                  >
                    {tier}%
                  </button>
                ))}
              </div>

              <motion.div
                animate={{ opacity: 1 }}
                initial={false}
                className="grid grid-cols-2 gap-3 bg-muted/50 rounded-lg p-4 mt-1"
              >
                <div>
                  <div className="text-xs text-muted-foreground">Desconto ao usuário</div>
                  <div className="text-lg font-bold font-mono text-foreground">{discountPct}%</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground">Você recebe a cada R$100 vendidos</div>
                  <div className="text-lg font-bold font-mono text-emerald-500">R$ {commissionPer100(discountPct)}</div>
                </div>
              </motion.div>
            </div>

            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : (<>Enviar solicitação <ArrowRight className="w-4 h-4 ml-2" /></>)}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              Já é parceiro? <Link href="/entrar" className="text-primary hover:underline">Entrar</Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
