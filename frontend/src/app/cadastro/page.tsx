"use client";
import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, ArrowRight, CheckCircle2, Mail } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

type Step = "dados" | "otp" | "senha";

export default function CadastroPage() {
  const { setSession } = useAuth();
  const router = useRouter();
  const [step, setStep] = useState<Step>("dados");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [form, setForm] = useState({ full_name: "", email: "", cpf: "", phone: "" });
  const [code, setCode] = useState("");
  const [setupToken, setSetupToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const upd = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submitDados(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      await authApi.register({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        cpf: form.cpf.replace(/\D/g, ""),
        phone: form.phone.replace(/\D/g, ""),
      });
      setStep("otp");
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  async function submitOtp(e: React.FormEvent) {
    e.preventDefault();
    setErr(null); setBusy(true);
    try {
      const { setup_token } = await authApi.verifyEmail(form.email.trim(), code.trim());
      setSetupToken(setup_token);
      setStep("senha");
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  async function submitSenha(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (password !== confirm) { setErr("As senhas não coincidem."); return; }
    setBusy(true);
    try {
      const t = await authApi.setPassword(setupToken, password);
      await setSession(t);
      router.push("/");
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="max-w-md mx-auto mt-6 sm:mt-12">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Criar conta</CardTitle>
          <CardDescription>
            <span className="flex items-center gap-2 mt-1">
              {(["dados", "otp", "senha"] as Step[]).map((s, i) => (
                <span key={s} className={`h-1.5 flex-1 rounded-full ${["dados", "otp", "senha"].indexOf(step) >= i ? "bg-primary" : "bg-muted"}`} />
              ))}
            </span>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {err && <div className="mb-4 text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

          {step === "dados" && (
            <form onSubmit={submitDados} className="space-y-3.5">
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
                  <Label htmlFor="tel">Telefone</Label>
                  <Input id="tel" value={form.phone} onChange={upd("phone")} placeholder="(11) 90000-0000" required />
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : (<>Continuar <ArrowRight className="w-4 h-4 ml-2" /></>)}
              </Button>
              <p className="text-center text-sm text-muted-foreground">
                Já tem conta? <Link href="/entrar" className="text-primary hover:underline">Entrar</Link>
              </p>
            </form>
          )}

          {step === "otp" && (
            <form onSubmit={submitOtp} className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Mail className="w-4 h-4" /> Enviamos um código para <b className="text-foreground">{form.email}</b>.
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="code">Código de verificação</Label>
                <Input id="code" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  inputMode="numeric" maxLength={6} placeholder="000000" className="text-center text-2xl tracking-[0.5em] font-mono" required />
              </div>
              <Button type="submit" className="w-full" disabled={busy || code.length < 4}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Verificar"}
              </Button>
              <button type="button" className="text-sm text-muted-foreground hover:text-foreground w-full"
                onClick={() => authApi.resendOtp(form.email.trim()).then(() => setErr(null)).catch((e) => setErr((e as Error).message))}>
                Reenviar código
              </button>
            </form>
          )}

          {step === "senha" && (
            <form onSubmit={submitSenha} className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-emerald-600">
                <CheckCircle2 className="w-4 h-4" /> E-mail verificado. Crie sua senha.
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pw">Senha</Label>
                <Input id="pw" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="mín. 8 caracteres, com letras e números" required autoComplete="new-password" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pw2">Confirmar senha</Label>
                <Input id="pw2" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required autoComplete="new-password" />
              </div>
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Concluir cadastro"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
