"use client";
import React from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

// Aviso explícito quando o servidor recusa o token em pleno uso (sessão expirada de
// verdade) — antes disso o usuário via a tela "deslogar" sem nenhuma explicação.
export default function SessionExpiredNotice() {
  const { sessionExpiredMsg, dismissSessionExpiredMsg } = useAuth();
  const router = useRouter();

  if (!sessionExpiredMsg) return null;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) dismissSessionExpiredMsg(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Sessão expirada</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">{sessionExpiredMsg}</p>
        <Button className="w-full" onClick={() => { dismissSessionExpiredMsg(); router.push("/entrar"); }}>
          Fazer login novamente
        </Button>
      </DialogContent>
    </Dialog>
  );
}
