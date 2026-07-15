"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/AuthContext";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

const IDLE_MS = 5 * 60 * 1000; // 5 minutos sem interação
const GRACE_MS = 60 * 1000;    // 1 minuto para responder antes do logout automático
const ACTIVITY_EVENTS = ["mousemove", "keydown", "click", "scroll", "touchstart"] as const;

// Vigia inatividade do usuário logado: após 5 minutos sem interação, avisa com um
// diálogo; se ninguém responder em mais 1 minuto, desloga automaticamente.
export default function InactivityWatcher() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [warningOpen, setWarningOpen] = useState(false);
  const idleTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const graceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const warningOpenRef = useRef(false);

  const doLogout = useCallback(() => {
    setWarningOpen(false);
    logout();
    router.push("/");
  }, [logout, router]);

  const resetTimer = useCallback(() => {
    if (idleTimer.current) clearTimeout(idleTimer.current);
    if (graceTimer.current) clearTimeout(graceTimer.current);
    setWarningOpen(false);
    idleTimer.current = setTimeout(() => {
      setWarningOpen(true);
      graceTimer.current = setTimeout(doLogout, GRACE_MS);
    }, IDLE_MS);
  }, [doLogout]);

  useEffect(() => { warningOpenRef.current = warningOpen; }, [warningOpen]);

  useEffect(() => {
    if (!user) {
      if (idleTimer.current) clearTimeout(idleTimer.current);
      if (graceTimer.current) clearTimeout(graceTimer.current);
      setWarningOpen(false);
      return;
    }
    const handler = () => { if (!warningOpenRef.current) resetTimer(); };
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, handler));
    resetTimer();
    return () => {
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, handler));
      if (idleTimer.current) clearTimeout(idleTimer.current);
      if (graceTimer.current) clearTimeout(graceTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, resetTimer]);

  if (!user) return null;

  return (
    <Dialog open={warningOpen} onOpenChange={(open) => { if (!open) resetTimer(); }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Você ainda está aí?</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Notamos que você ficou inativo por alguns minutos. Por segurança, sua sessão será encerrada em breve caso não haja resposta.
        </p>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" size="sm" onClick={doLogout}>Sair agora</Button>
          <Button size="sm" onClick={resetTimer}>Continuar conectado</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
