"use client";
import React, { useCallback, useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { securityApi, IncidentType } from "@/lib/securityApi";
import { useAuth } from "@/lib/AuthContext";

// Envolve as análises geradas: bloqueia cópia/menu de contexto/impressão e detecta a
// tecla PrintScreen (único sinal de captura de tela que o navegador expõe — capturas via
// ferramentas do sistema operacional não são detectáveis por JS). Ao detectar, borra o
// conteúdo, mostra um aviso e registra o incidente para revisão manual do time.
export default function ScreenshotGuard({ children, page }: { children: React.ReactNode; page: string }) {
  const { user } = useAuth();
  const [triggered, setTriggered] = useState(false);
  const [backgrounded, setBackgrounded] = useState(false);
  const isAdmin = user && (user.role === "owner" || user.role === "manager" || user.email === "valerioeducfin@gmail.com");

  const report = useCallback((incident_type: IncidentType) => {
    if (!user) return; // só usuários autenticados geram análises protegidas
    securityApi.reportIncident({ incident_type, page }).catch(() => {});
  }, [user, page]);

  const trigger = useCallback((incident_type: IncidentType) => {
    setTriggered(true);
    report(incident_type);
  }, [report]);

  useEffect(() => {
    if (isAdmin) return; // admin não tem nenhuma restrição de impressão/cópia/captura
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === "PrintScreen") trigger("printscreen");
    };
    document.addEventListener("keyup", onKeyUp);
    return () => document.removeEventListener("keyup", onKeyUp);
  }, [trigger, isAdmin]);

  // Mobile não dispara PrintScreen (captura é por gesto do SO, sem evento de teclado) —
  // a mitigação possível aqui é borrar/escurecer o conteúdo assim que o app perde foco
  // (troca de app, gravação de tela, câmera aberta para fotografar a tela), cobrindo uma
  // fração maior dos casos reais em mobile. Não é reportado como incidente (visibilitychange
  // dispara toda troca de app — reportar isso geraria ruído sem sinal real de captura).
  useEffect(() => {
    if (isAdmin) return;
    const onVisibility = () => setBackgrounded(document.hidden);
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [isAdmin]);

  const blockCopy = (e: React.ClipboardEvent) => { e.preventDefault(); report("copy_blocked"); };
  const blockContextMenu = (e: React.MouseEvent) => { e.preventDefault(); report("context_menu_blocked"); };

  if (isAdmin) return <>{children}</>;

  return (
    <div className="relative">
      <div
        onCopy={blockCopy}
        onContextMenu={blockContextMenu}
        className={`select-none [-webkit-touch-callout:none] print:hidden transition-[filter,opacity] duration-200 ${(triggered || backgrounded) ? "blur-xl brightness-50 pointer-events-none" : ""}`}
      >
        {children}
      </div>

      {/* Substitui o conteúdo ao imprimir (Ctrl+P) — a análise não sai impressa. */}
      <div className="hidden print:flex items-center justify-center p-16 text-center text-sm text-muted-foreground">
        Esta análise é individual e exclusiva da sua sessão — a impressão não é permitida.
      </div>

      {triggered && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-background/80 backdrop-blur-sm">
          <div className="max-w-md w-full rounded-2xl border-2 border-red-500/50 bg-card shadow-2xl p-6 text-center">
            <ShieldAlert className="w-10 h-10 text-red-500 mx-auto mb-3" />
            <h3 className="text-lg font-bold mb-2">Captura de tela detectada</h3>
            <p className="text-sm text-muted-foreground mb-4 leading-relaxed">
              Esta análise é individual e exclusiva da sua sessão — compartilhar as informações
              geradas viola os Termos de Uso. Este evento foi registrado e o padrão de uso da sua
              conta é monitorado; reincidências podem levar ao consumo de créditos e à suspensão
              temporária da conta.
            </p>
            <button
              onClick={() => setTriggered(false)}
              className="px-5 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:opacity-90 transition-opacity"
            >
              Entendi
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
