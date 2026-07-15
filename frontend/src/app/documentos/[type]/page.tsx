"use client";
import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, CheckCircle2, Loader2 } from "lucide-react";
import { legalApi } from "@/lib/monetizationApi";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function DocumentoPage() {
  const params = useParams();
  const router = useRouter();
  const type = String(params.type);
  const [doc, setDoc] = useState<{ id: string; title: string; version: number; body_md: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pendingIds, setPendingIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, pending] = await Promise.all([
        legalApi.document(type),
        legalApi.pending().catch(() => []),
      ]);
      setDoc(d);
      setPendingIds(pending.map((p) => p.id));
    } catch (e) {
      setErr((e as Error).message);
    }
  }, [type]);

  useEffect(() => { load(); }, [load]);

  const isPending = !!doc && pendingIds.includes(doc.id);

  async function sign() {
    if (!doc) return;
    setBusy(true);
    try {
      await legalApi.accept([doc.id]);
      setAccepted(true);
      await load();
    } finally {
      setBusy(false);
    }
  }

  if (err) return <div className="max-w-3xl mx-auto text-sm text-red-600">{err}</div>;
  if (!doc) return <div className="flex justify-center py-20"><Loader2 className="w-6 h-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <Link href="/documentos" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft className="w-4 h-4" /> Retornar para Documentos
      </Link>
      <Card>
        <CardContent className="pt-6 prose prose-sm dark:prose-invert max-w-none">
          <div className="text-xs text-muted-foreground mb-2">Versão {doc.version}</div>
          {/* renderizacao simples de markdown (paragrafos e titulos) */}
          {doc.body_md.split("\n").map((line, i) => {
            if (line.startsWith("## ")) return <h2 key={i} className="text-lg font-semibold mt-3 mb-2">{line.slice(3)}</h2>;
            if (line.startsWith("# ")) return <h1 key={i} className="text-xl font-bold mt-2 mb-3">{line.slice(2)}</h1>;
            if (!line.trim()) return <div key={i} className="h-2" />;
            return <p key={i} className="text-sm text-muted-foreground leading-relaxed">{line}</p>;
          })}

          <div className="not-prose border-t border-border/50 mt-6 pt-4 flex items-center justify-between gap-3 flex-wrap">
            {isPending ? (
              <>
                <p className="text-xs text-muted-foreground">Ao clicar em "Assinar", você confirma que leu e concorda com este documento.</p>
                <Button size="sm" disabled={busy} onClick={sign}>
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Assinar / Aceitar"}
                </Button>
              </>
            ) : (
              <span className="text-sm text-emerald-600 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Você já aceitou esta versão.</span>
            )}
          </div>
          {accepted && (
            <p className="not-prose text-xs text-emerald-600 mt-2">Documento assinado com sucesso.</p>
          )}

          <div className="not-prose mt-4">
            <Link href="/documentos"><Button variant="outline" size="sm">Retornar para Documentos</Button></Link>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
