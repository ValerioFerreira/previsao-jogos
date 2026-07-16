"use client";
import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { legalApi, type LegalDoc } from "@/lib/monetizationApi";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

// Avisa o usuário logado quando um documento que ele já havia aceitado foi republicado
// pelo admin (nova versão vigente, ver legal/service.py::publish — sempre exige novo
// aceite). Um "Depois" só adia dentro da mesma aba/sessão (sessionStorage) — a compra de
// créditos continua bloqueada de verdade pelo gate já existente na Carteira.
const DISMISS_KEY = "apostai:legal_gate_dismissed_ids";

export default function LegalGate() {
  const { user } = useAuth();
  const router = useRouter();
  const [pending, setPending] = useState<LegalDoc[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!user) {
      setOpen(false);
      setPending([]);
      return;
    }
    legalApi.pending().then((docs) => {
      if (docs.length === 0) return;
      let dismissed: string[] = [];
      try {
        dismissed = JSON.parse(sessionStorage.getItem(DISMISS_KEY) || "[]");
      } catch { /* ignora */ }
      const stillPending = docs.filter((d) => !dismissed.includes(d.id));
      if (stillPending.length > 0) {
        setPending(docs);
        setOpen(true);
      }
    }).catch(() => {});
  }, [user]);

  function dismiss() {
    try {
      sessionStorage.setItem(DISMISS_KEY, JSON.stringify(pending.map((d) => d.id)));
    } catch { /* ignora */ }
    setOpen(false);
  }

  if (!user || pending.length === 0) return null;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) dismiss(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Documentos atualizados</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          {pending.length === 1
            ? "Um documento que você já havia aceitado foi atualizado."
            : `${pending.length} documentos que você já havia aceitado foram atualizados.`}
          {" "}É necessário revisar e assinar novamente para continuar usando a plataforma normalmente.
        </p>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={dismiss}>Depois</Button>
          <Button onClick={() => { setOpen(false); router.push("/documentos"); }}>Revisar agora</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
