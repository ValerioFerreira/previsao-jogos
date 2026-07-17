"use client";
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LayoutDashboard, Sparkles, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { authApi } from "@/lib/authApi";
import { Card, CardContent } from "@/components/ui/card";

export default function ParceiroHubPage() {
  const { user, loading, setSession } = useAuth();
  const router = useRouter();
  const [enteringDemo, setEnteringDemo] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/entrar");
  }, [loading, user, router]);

  async function enterDemo() {
    setErr(null);
    setEnteringDemo(true);
    try {
      const t = await authApi.enterDemo();
      await setSession(t);
      router.push("/");
    } catch (e) {
      setErr((e as Error).message);
      setEnteringDemo(false);
    }
  }

  if (loading || !user) {
    return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;
  }

  return (
    <div className="max-w-lg mx-auto mt-6 sm:mt-16 space-y-6">
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold">Olá, {user.full_name.split(" ")[0]}</h1>
        <p className="text-sm text-muted-foreground">O que você quer fazer agora?</p>
      </div>

      {err && <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-3">{err}</div>}

      <div className="grid sm:grid-cols-2 gap-4">
        <button onClick={enterDemo} disabled={enteringDemo} className="text-left">
          <Card className="h-full hover:border-primary/60 transition-colors">
            <CardContent className="pt-6 pb-6 flex flex-col items-center text-center gap-3">
              <div className="w-11 h-11 rounded-full bg-primary/10 flex items-center justify-center">
                {enteringDemo ? <Loader2 className="w-5 h-5 animate-spin text-primary" /> : <Sparkles className="w-5 h-5 text-primary" />}
              </div>
              <div>
                <div className="font-semibold">Ir para conta Demo</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Use o site como um usuário comum, com créditos ilimitados, para mostrar a plataforma ao seu público.
                </p>
              </div>
            </CardContent>
          </Card>
        </button>

        <button onClick={() => router.push("/parceiro/dashboard")} className="text-left">
          <Card className="h-full hover:border-primary/60 transition-colors">
            <CardContent className="pt-6 pb-6 flex flex-col items-center text-center gap-3">
              <div className="w-11 h-11 rounded-full bg-primary/10 flex items-center justify-center">
                <LayoutDashboard className="w-5 h-5 text-primary" />
              </div>
              <div>
                <div className="font-semibold">Dashboard</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Veja seu código, cliques, vendas e comissão a receber do seu programa de parceria.
                </p>
              </div>
            </CardContent>
          </Card>
        </button>
      </div>
    </div>
  );
}
