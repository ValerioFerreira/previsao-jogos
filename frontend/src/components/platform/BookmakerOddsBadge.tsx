"use client";
import React, { useState } from "react";
import { Landmark, TrendingUp } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import type { BookmakerOddEntry } from "@/lib/api";

// Verificador de Bets: badge pequeno (mesmo padrão visual do InfoTooltip) que, ao
// clicar, abre um modal com as odds de cada casa cadastrada para aquele
// mercado/outcome específico, ordenadas da maior para a menor, destacando em verde
// as que pagam >= a odd mínima da faixa de odd justa do modelo (nenhum cálculo novo
// aqui -- fairMin já vem de prediction.odds.*.faixa_odd_justa do /predict).
export default function BookmakerOddsBadge({
  label,
  entries,
  fairMin,
}: {
  label: string;
  entries: BookmakerOddEntry[] | undefined | null;
  fairMin?: number;
}) {
  const [open, setOpen] = useState(false);

  // Só renderiza quando o mercado/outcome tem pelo menos 2 casas cadastradas
  // (comparação só faz sentido com mais de uma opção).
  if (!entries || entries.length < 2) return null;

  return (
    <>
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => setOpen(true)}
              className="inline-flex items-center gap-1 ml-1 px-1.5 py-0.5 rounded-md border border-border/60 bg-muted/40 text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              aria-label={`Ver odds de ${entries.length} casas de apostas`}
            >
              <Landmark className="w-3 h-3" />
              {entries.length} casas
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed">
            <p>Odds de {entries.length} casas cadastradas. Clique para ver o ranking.</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>
              Odds por casa de apostas, da maior para a menor.
              {fairMin != null && (
                <>
                  {" "}Em <span className="text-emerald-400 font-medium">verde</span>, as que pagam
                  na ou acima da faixa de odd justa do nosso modelo (≥ {fairMin.toFixed(2)}).
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-80 overflow-y-auto space-y-1.5 pr-1">
            {entries.map((e, i) => {
              const highlight = fairMin != null && e.odd >= fairMin;
              return (
                <div
                  key={`${e.casa}-${i}`}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg border text-sm ${
                    highlight
                      ? "bg-emerald-500/10 border-emerald-500/30"
                      : "bg-muted/30 border-border/30"
                  }`}
                >
                  <span className="font-medium text-foreground flex items-center gap-1.5 truncate">
                    {highlight && <TrendingUp className="w-3.5 h-3.5 text-emerald-400 shrink-0" />}
                    <span className="truncate">{e.casa}</span>
                  </span>
                  <span className={`font-mono font-bold shrink-0 ml-2 ${highlight ? "text-emerald-400" : "text-foreground"}`}>
                    {e.odd.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
