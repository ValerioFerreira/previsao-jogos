"use client";
import React, { useEffect, useRef, useState } from "react";
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
const HERO_BG_URL =
  "https://media.istockphoto.com/id/1262691718/photo/man-giving-fist-bump-monochrome-black-and-white-image.jpg?s=612x612&w=0&k=20&c=wLXYOXzge6nsMC4f-KSYvP2d8G2nNREmFVQbGFsKzWU=";

function commissionPer100(discountPct: number): string {
  const commissionRatePct = COMMISSION_BUDGET_PCT - discountPct;
  const paidPer100 = 100 - discountPct;
  return ((commissionRatePct * paidPer100) / 100).toFixed(2);
}

function maskCpf(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  let out = d.slice(0, 3);
  if (d.length > 3) out += "." + d.slice(3, 6);
  if (d.length > 6) out += "." + d.slice(6, 9);
  if (d.length > 9) out += "-" + d.slice(9, 11);
  return out;
}

function maskPhone(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  if (!d) return "";
  if (d.length <= 2) return `(${d}`;
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7, 11)}`;
}

export default function SolicitarParceriaPage() {
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [form, setForm] = useState({ full_name: "", email: "", cpf: "", phone: "" });
  const [paymentType, setPaymentType] = useState<"pf" | "pj">("pf");
  const [discountPct, setDiscountPct] = useState(15);

  const [codePrefix, setCodePrefix] = useState("");
  const [codeTouched, setCodeTouched] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const suggestTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sugestão automática de código (nome + desconto) enquanto o parceiro não editar o
  // prefixo manualmente — o sufixo numérico do desconto nunca é editável (ver backend).
  useEffect(() => {
    if (codeTouched || !form.full_name.trim()) return;
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    suggestTimer.current = setTimeout(() => {
      setSuggesting(true);
      affiliatesApi.suggestCode(form.full_name.trim(), discountPct)
        .then((s) => setCodePrefix(s.prefix))
        .catch(() => {})
        .finally(() => setSuggesting(false));
    }, 400);
    return () => { if (suggestTimer.current) clearTimeout(suggestTimer.current); };
  }, [form.full_name, discountPct, codeTouched]);

  const updName = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, full_name: e.target.value.toUpperCase() }));
  const updEmail = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, email: e.target.value.toLowerCase() }));
  const updCpf = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, cpf: maskCpf(e.target.value) }));
  const updPhone = (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, phone: maskPhone(e.target.value) }));

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
        code_prefix: codePrefix.trim() || undefined,
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
      <Card className="overflow-hidden">
        <CardHeader className="relative p-0">
          <div
            aria-hidden
            className="absolute inset-0 bg-cover bg-center"
            style={{ backgroundImage: `url(${HERO_BG_URL})` }}
          />
          <div aria-hidden className="absolute inset-0 bg-gradient-to-b from-slate-950/55 via-slate-950/80 to-card" />
          <div className="relative px-6 py-10 sm:py-12 flex flex-col items-center text-center gap-2">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
              <CardTitle className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
                Seja um <span className="bg-gradient-to-r from-emerald-400 to-cyan-400 bg-clip-text text-transparent">Parceiro</span>
              </CardTitle>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.12 }}>
              <CardDescription className="text-white/90 max-w-sm text-sm sm:text-base">
                Divulgue o ApostAIinfo com seu próprio código de desconto e ganhe comissão!
              </CardDescription>
            </motion.div>
          </div>
        </CardHeader>
        <CardContent className="pt-6">
          {err && <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="nome">Nome completo</Label>
              <Input id="nome" value={form.full_name} onChange={updName} required />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">E-mail</Label>
              <Input id="email" type="email" value={form.email} onChange={updEmail} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="cpf">CPF</Label>
                <Input
                  id="cpf" value={form.cpf} onChange={updCpf} placeholder="000.000.000-00"
                  className="placeholder:text-muted-foreground/40" inputMode="numeric" maxLength={14} required
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="tel">Telefone (WhatsApp)</Label>
                <Input
                  id="tel" value={form.phone} onChange={updPhone} placeholder="(11) 90000-0000"
                  className="placeholder:text-muted-foreground/40" inputMode="numeric" maxLength={15} required
                />
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
                  <div className="text-xs text-muted-foreground">A cada R$100 em compras no site com seu código, você recebe:</div>
                  <div className="text-lg font-bold font-mono text-emerald-500">R$ {commissionPer100(discountPct)}</div>
                </div>
              </motion.div>
            </div>

            <div className="space-y-1.5">
              <Label className="flex items-center" htmlFor="code_prefix">
                Seu código de desconto
                <InfoTooltip text="Sugerimos automaticamente a partir do seu nome. Você pode editar a parte em texto, mas o número do final é sempre o seu desconto e não pode ser alterado." />
              </Label>
              <div className="flex items-center gap-0 rounded-md border border-input bg-transparent overflow-hidden focus-within:ring-1 focus-within:ring-ring">
                <input
                  id="code_prefix"
                  value={codePrefix}
                  onChange={(e) => { setCodeTouched(true); setCodePrefix(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "")); }}
                  placeholder="SEUNOME"
                  maxLength={20}
                  className="flex-1 h-9 px-3 py-1 text-sm bg-transparent outline-none placeholder:text-muted-foreground/40 font-mono uppercase"
                />
                <span className="h-9 px-3 flex items-center text-sm font-mono font-semibold bg-muted text-muted-foreground shrink-0">
                  {discountPct}
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                {suggesting ? "Gerando sugestão…" : `Código final: ${(codePrefix || "SEUNOME").toUpperCase()}${discountPct}`}
              </p>
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
