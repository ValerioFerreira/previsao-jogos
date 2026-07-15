"use client";
import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { FileText, CheckCircle2, Loader2 } from "lucide-react";
import { legalApi, type LegalDoc } from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function DocumentosPage() {
  const [docs, setDocs] = useState<LegalDoc[]>([]);
  const [pending, setPending] = useState<LegalDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [d, p] = await Promise.all([
      legalApi.documents().catch(() => []),
      legalApi.pending().catch(() => []),
    ]);
    setDocs(d);
    setPending(p);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  async function accept(id: string) {
    setBusyId(id);
    try {
      await legalApi.accept([id]);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2"><FileText className="w-6 h-6" /> Documentos e Termos</h1>

      <Card>
        <CardHeader><CardTitle className="text-lg">Documentos vigentes</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {pending.length > 0 && (
            <div className="mb-3 text-sm rounded-md bg-amber-500/10 text-amber-600 p-3">
              Você tem {pending.length} documento(s) pendente(s) de aceite. É necessário aceitar todos antes de realizar compras de créditos.
            </div>
          )}
          {loading ? (
            <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-muted-foreground" /></div>
          ) : (
            docs.map((d) => {
              const isPending = pending.some((p) => p.id === d.id);
              return (
                <div key={d.id} className="flex items-center justify-between border-b border-border/30 py-2.5 text-sm">
                  <Link href={`/documentos/${d.type}`} className="hover:underline">
                    {d.title} <span className="text-xs text-muted-foreground">v{d.version}</span>
                  </Link>
                  {isPending
                    ? (
                      <Button size="sm" disabled={busyId === d.id} onClick={() => accept(d.id)}>
                        {busyId === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : "Aceitar"}
                      </Button>
                    )
                    : <span className="text-xs text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Aceito</span>}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
