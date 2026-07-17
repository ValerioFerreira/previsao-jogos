"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Loader2 } from "lucide-react";
import { useAuth } from "@/lib/AuthContext";
import { adminApi } from "@/lib/adminApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STATUS_LABEL: Record<string, string> = {
  pending: "Pendente", active: "Ativo", paused: "Pausado", rejected: "Rejeitado",
};

function fmt(d: string) { return new Date(d).toLocaleString("pt-BR"); }

export default function PartnerDetailPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const id = String(params.id);
  const isAdmin = user && (user.role === "admin" || user.role === "superadmin");

  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { if (!loading && !isAdmin) router.replace("/"); }, [loading, isAdmin, router]);

  const load = useCallback(async () => {
    try { setDetail(await adminApi.affiliateDetail(id)); } catch (e) { setErr((e as Error).message); }
  }, [id]);

  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  if (!isAdmin || !detail) {
    return (
      <div className="flex justify-center py-20">
        {err ? <div className="text-sm rounded-md bg-red-500/10 text-red-600 p-4">{err}</div> : <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />}
      </div>
    );
  }

  const payments = (detail.payments as Record<string, unknown>[]) || [];
  const demoLogs = (detail.demo_access_logs as Record<string, unknown>[]) || [];

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link href="/admin"><ArrowLeft className="w-4 h-4 text-muted-foreground hover:text-foreground" /></Link>
        <h1 className="text-2xl font-bold">{String(detail.name)}</h1>
        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
          {STATUS_LABEL[String(detail.status)] ?? String(detail.status)}
        </span>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-lg">Dados cadastrais</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 gap-4 text-sm">
          <div><div className="text-xs text-muted-foreground">Código</div><div className="font-mono">{String(detail.code)}</div></div>
          <div><div className="text-xs text-muted-foreground">Forma de pagamento</div><div>{String(detail.payment_type ?? "—").toUpperCase()}</div></div>
          <div><div className="text-xs text-muted-foreground">E-mail</div><div>{String(detail.contact_email ?? "—")}</div></div>
          <div><div className="text-xs text-muted-foreground">Telefone</div><div>{String(detail.contact_phone ?? "—")}</div></div>
          <div><div className="text-xs text-muted-foreground">Desconto do cupom</div><div>{detail.discount_pct ? `${String(detail.discount_pct)}%` : "—"}</div></div>
          <div><div className="text-xs text-muted-foreground">Comissão</div><div>{detail.commission_pct ? `${String(detail.commission_pct)}%` : "—"}</div></div>
          <div><div className="text-xs text-muted-foreground">Status da conta</div><div>{String(detail.account_status ?? "sem conta")}</div></div>
          <div><div className="text-xs text-muted-foreground">Acesso à conta demo</div><div>{detail.demo_access_enabled ? "permitido" : "revogado"}</div></div>
          {detail.notes ? <div className="col-span-2"><div className="text-xs text-muted-foreground">Notas</div><div>{String(detail.notes)}</div></div> : null}
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Cliques", value: String(detail.clicks ?? 0) },
          { label: "Cadastros", value: String(detail.signups ?? 0) },
          { label: "Compradores", value: String(detail.buyers ?? 0) },
          { label: "Faturamento", value: `R$ ${Number(detail.revenue_brl ?? 0).toFixed(0)}` },
        ].map((s) => (
          <Card key={s.label}>
            <CardContent className="pt-6 text-center">
              <div className="text-2xl font-bold">{s.value}</div>
              <div className="text-xs text-muted-foreground">{s.label}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão devida</div>
            <div className="text-2xl font-bold text-amber-500">R$ {Number(detail.commission_due_brl ?? 0).toFixed(2)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-sm text-muted-foreground">Comissão já paga</div>
            <div className="text-2xl font-bold text-emerald-600">R$ {Number(detail.commission_paid_brl ?? 0).toFixed(2)}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-lg">Histórico de pagamentos</CardTitle></CardHeader>
        <CardContent>
          {payments.length === 0 && <p className="text-sm text-muted-foreground">Nenhum pagamento registrado ainda.</p>}
          {payments.map((p) => (
            <div key={String(p.id)} className="flex items-center justify-between py-2 border-b last:border-0 text-sm">
              <div>
                <div className="font-mono">R$ {String(p.amount_brl)}</div>
                <div className="text-xs text-muted-foreground">{p.method ? String(p.method) : "—"} · {p.paid_at ? fmt(String(p.paid_at)) : "—"}</div>
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">{String(p.status)}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-lg">Acessos à conta demo</CardTitle></CardHeader>
        <CardContent>
          {demoLogs.length === 0 && <p className="text-sm text-muted-foreground">Nenhum acesso registrado ainda.</p>}
          {demoLogs.map((l, i) => (
            <div key={i} className="flex items-center justify-between py-2 border-b last:border-0 text-sm">
              <div className="font-mono text-xs">{String(l.cpf_used)}</div>
              <div className="text-xs text-muted-foreground">{fmt(String(l.created_at))} · {String(l.ip ?? "—")}</div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
