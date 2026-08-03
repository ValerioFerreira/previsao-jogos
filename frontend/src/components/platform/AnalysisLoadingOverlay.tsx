"use client";
import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle2, Loader2 } from 'lucide-react';

// Mensagens em sequência (~1s de ritmo cada) enquanto o /predict real está em voo.
// A última ("Concluído!") só aparece quando a resposta de verdade chega — nunca é
// forçada por delay artificial. Se a resposta chegar antes da sequência terminar,
// pulamos direto para "Concluído!" (não trava a UI esperando a animação acabar).
const STEPS = [
  "Carregando partida...",
  "Iniciando modelos...",
  "Efetuando cálculos...",
  "Refinando resultados...",
];
const STEP_MS = 950; // ritmo de cada mensagem intermediária
const DONE_HOLD_MS = 550; // quanto tempo "Concluído!" fica visível antes de sumir

/**
 * Animação de carregamento da geração de análise: barra de progresso + mensagens
 * em sequência. `loading` é a flag real de request em voo (handleGenerate em
 * app/page.tsx) — o componente é sempre montado, mas só fica visível enquanto
 * `loading` é true ou durante o breve flourish de conclusão logo depois.
 */
export function AnalysisLoadingOverlay({ loading }: { loading: boolean }) {
  const [visible, setVisible] = React.useState(false);
  const [stepIndex, setStepIndex] = React.useState(0);
  const [done, setDone] = React.useState(false);
  const wasLoadingRef = React.useRef(false);

  React.useEffect(() => {
    if (loading) {
      // novo request começando: reseta a sequência do zero.
      wasLoadingRef.current = true;
      setVisible(true);
      setDone(false);
      setStepIndex(0);

      const interval = setInterval(() => {
        setStepIndex((i) => (i < STEPS.length - 1 ? i + 1 : i));
      }, STEP_MS);
      return () => clearInterval(interval);
    }

    // loading virou false: só reage se de fato vínhamos de um request em voo
    // (evita disparar o flourish no mount inicial, quando loading já nasce false).
    if (!wasLoadingRef.current) return;
    wasLoadingRef.current = false;
    setDone(true);
    const hide = setTimeout(() => setVisible(false), DONE_HOLD_MS);
    return () => clearTimeout(hide);
  }, [loading]);

  const progressPct = done ? 100 : Math.round(((stepIndex + 1) / (STEPS.length + 1)) * 100);
  const label = done ? "Concluído!" : STEPS[stepIndex];

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25 }}
          className="w-full max-w-md bg-card border border-border/50 rounded-xl p-4 sm:p-5 flex flex-col gap-3"
        >
          <div className="flex items-center gap-2.5">
            {done
              ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
              : <Loader2 className="w-4 h-4 text-cyan-500 shrink-0 animate-spin" />}
            {/* Troca de texto sem depender de uma coreografia exit/enter encadeada
                (nested AnimatePresence) -- um key simples + transição CSS já dá o
                crossfade sutil, sem risco de travar o "Concluído!" atrás de uma
                animação anterior que não terminou (aba em segundo plano throttla
                requestAnimationFrame, por exemplo). */}
            <span key={label} className={`text-sm font-medium animate-in fade-in duration-200 ${done ? 'text-emerald-500' : 'text-foreground'}`}>
              {label}
            </span>
          </div>

          <div className="w-full h-1.5 rounded-full bg-muted/40 overflow-hidden">
            <motion.div
              className={`h-full rounded-full ${done ? 'bg-emerald-500' : 'bg-gradient-to-r from-emerald-500 to-cyan-500'}`}
              animate={{ width: `${progressPct}%` }}
              transition={{ duration: 0.5, ease: "easeOut" }}
            />
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default AnalysisLoadingOverlay;
