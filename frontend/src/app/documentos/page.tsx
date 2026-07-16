"use client";
import React, { useEffect, useState, useCallback } from "react";
import { FileText, CheckCircle2, Loader2, ChevronDown } from "lucide-react";
import { legalApi, type LegalDoc } from "@/lib/monetizationApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type DocBody = { id: string; title: string; version: number; body_md: string };

function renderBody(body_md: string) {
  return body_md.split("\n").map((line, i) => {
    if (line.startsWith("## ")) return <h2 key={i} className="text-base font-semibold mt-3 mb-1.5">{line.slice(3)}</h2>;
    if (line.startsWith("# ")) return <h1 key={i} className="text-lg font-bold mt-2 mb-2">{line.slice(2)}</h1>;
    if (!line.trim()) return <div key={i} className="h-2" />;
    return <p key={i} className="text-sm text-muted-foreground leading-relaxed">{line}</p>;
  });
}

export default function DocumentosPage() {
  const [docs, setDocs] = useState<LegalDoc[]>([]);
  const [pending, setPending] = useState<LegalDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [openType, setOpenType] = useState<string | null>(null);
  const [bodies, setBodies] = useState<Record<string, DocBody>>({});
  const [loadingBody, setLoadingBody] = useState<string | null>(null);

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

  async function toggle(type: string) {
    if (openType === type) {
      setOpenType(null);
      return;
    }
    setOpenType(type);
    if (!bodies[type]) {
      setLoadingBody(type);
      try {
        const doc = await legalApi.document(type);
        setBodies((prev) => ({ ...prev, [type]: doc }));
      } finally {
        setLoadingBody(null);
      }
    }
  }

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
              const isOpen = openType === d.type;
              const body = bodies[d.type];
              return (
                <div key={d.id} className="border-b border-border/30 last:border-b-0">
                  <button
                    onClick={() => toggle(d.type)}
                    className="w-full flex items-center justify-between py-2.5 text-sm text-left hover:text-primary transition-colors"
                  >
                    <span className="flex items-center gap-2">
                      <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOpen ? "rotate-180" : ""}`} />
                      {d.title} <span className="text-xs text-muted-foreground">v{d.version}</span>
                    </span>
                    {isPending
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-amber-500" />
                      : <span className="text-xs text-emerald-600 flex items-center gap-1"><CheckCircle2 className="w-3.5 h-3.5" /> Aceito</span>}
                  </button>
                  {isOpen && (
                    <div className="pb-4 pl-5">
                      {loadingBody === d.type ? (
                        <div className="flex justify-center py-6"><Loader2 className="w-4 h-4 animate-spin text-muted-foreground" /></div>
                      ) : body ? (
                        <div className="prose prose-sm dark:prose-invert max-w-none">
                          {renderBody(body.body_md)}
                          <div className="not-prose border-t border-border/50 mt-4 pt-3 flex items-center justify-between gap-3 flex-wrap">
                            {isPending ? (
                              <>
                                <p className="text-xs text-muted-foreground">Ao clicar em "Aceitar", você confirma que leu e concorda com este documento.</p>
                                <Button size="sm" disabled={busyId === d.id} onClick={() => accept(d.id)}>
                                  {busyId === d.id ? <Loader2 className="w-4 h-4 animate-spin" /> : "Aceitar"}
                                </Button>
                              </>
                            ) : (
                              <span className="text-sm text-emerald-600 flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Você já aceitou esta versão.</span>
                            )}
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
