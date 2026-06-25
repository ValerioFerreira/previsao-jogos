"use client";
import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import InfoTooltip from './InfoTooltip';

// Distribuição (PMF) + média projetada. Tudo (linhas O/U, odds) é derivado daqui,
// então o card não depende da grade de linhas fixa do backend.
type Distrib = { estimativa: number; distribuicao?: number[] };

type MarketCardProps = {
  title: string;
  subtitle?: string;
  prediction?: Distrib;
  // Quando há recortes por tempo, passe um mapa rótulo->distribuição; vira um seletor.
  periods?: Record<string, Distrib | undefined>;
  icon?: React.ReactNode;
};

// Faixa de "odd justa": da odd com margem de 7% para menos até a odd prevista (1/p).
function fairOddRange(prob: number): string {
  if (!prob || prob <= 0) return '—';
  const odd = 1 / prob;
  if (odd > 50) return '50+';
  return `${(odd * 0.93).toFixed(2)}–${odd.toFixed(2)}`;
}

// P(total > linha) a partir da PMF (linha é x.5): soma de dist[floor(L)+1 ..].
function overProb(dist: number[], line: number): number {
  const start = Math.floor(line) + 1;
  let s = 0;
  for (let k = start; k < dist.length; k++) s += dist[k];
  return Math.min(1, Math.max(0, s));
}

export function MarketCard({ title, subtitle, prediction, periods, icon }: MarketCardProps) {
  const [viewMode, setViewMode] = useState<'prob' | 'odd'>('odd');
  const [isExpanded, setIsExpanded] = useState(false);
  const periodKeys = periods ? Object.keys(periods).filter(k => periods[k]) : [];
  const [period, setPeriod] = useState<string>(periodKeys[0] ?? '');

  const active: Distrib | undefined = periods ? periods[period] : prediction;
  const dist = active?.distribuicao ?? [];
  const mean = active?.estimativa ?? 0;

  // Linha central = x.5 mais próxima da média; geramos 4 abaixo e 4 acima (>= 0.5).
  const { lines, mainLine } = useMemo(() => {
    const center = Math.round(mean - 0.5) + 0.5;
    const all: number[] = [];
    for (let i = -4; i <= 4; i++) {
      const L = center + i;
      if (L >= 0.5) all.push(Number(L.toFixed(1)));
    }
    return { lines: all, mainLine: all.includes(center) ? center : all[0] };
  }, [mean]);

  if (!active || dist.length === 0) return null;

  const Cell = ({ line, side }: { line: number; side: 'over' | 'under' }) => {
    const p = side === 'over' ? overProb(dist, line) : 1 - overProb(dist, line);
    return viewMode === 'prob'
      ? <span>{(p * 100).toFixed(1)}%</span>
      : <span>{fairOddRange(p)}</span>;
  };

  return (
    <div className="bg-card border border-border/50 rounded-xl overflow-hidden">
      <div className="p-4 border-b border-border/30 flex justify-between items-start gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold flex items-center gap-1.5">
            {icon}
            {subtitle ?? title}
            <InfoTooltip text="Média projetada é o valor esperado. A linha em destaque é a mais próxima da média. A faixa de odd justa vai da odd com 7% de margem até a odd prevista (1/probabilidade)." />
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Média Projetada: <span className="font-bold text-foreground">{mean.toFixed(1)}</span>
          </p>
        </div>
        <div className="bg-muted p-1 rounded-md flex text-[10px] font-medium shrink-0">
          <button
            onClick={() => setViewMode('prob')}
            className={`px-2 py-1 rounded transition-colors ${viewMode === 'prob' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Prob.</button>
          <button
            onClick={() => setViewMode('odd')}
            className={`px-2 py-1 rounded transition-colors ${viewMode === 'odd' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >Odd</button>
        </div>
      </div>

      {/* Seletor de tempo (1º tempo / 2º tempo / partida inteira) quando aplicável */}
      {periodKeys.length > 1 && (
        <div className="px-4 pt-3 flex gap-1.5 flex-wrap">
          {periodKeys.map(k => (
            <button
              key={k}
              onClick={() => setPeriod(k)}
              className={`px-2.5 py-1 rounded-md text-[10px] font-medium border transition-colors ${period === k ? 'bg-primary/10 border-primary/40 text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground'}`}
            >{k}</button>
          ))}
        </div>
      )}

      <div className="p-4">
        {/* Banner da linha principal (mais próxima da média) */}
        <div className="flex justify-between items-center mb-3 text-xs bg-muted/40 p-3 rounded-lg border border-border/40">
          <div className="flex-1 text-center">
            <span className="block text-muted-foreground mb-1">Over {mainLine}</span>
            <span className="font-mono font-bold text-emerald-400"><Cell line={mainLine} side="over" /></span>
          </div>
          <div className="flex-1 text-center border-l border-border/40">
            <span className="block text-muted-foreground mb-1">Under {mainLine}</span>
            <span className="font-mono font-bold text-blue-400"><Cell line={mainLine} side="under" /></span>
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-center gap-1 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? 'Ocultar Linhas Alternativas' : 'Ver Todas as Linhas'}
          <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
        </button>

        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pt-3 mt-1 border-t border-border/30">
                <div className="grid grid-cols-3 text-[10px] font-semibold text-muted-foreground uppercase pb-2">
                  <div className="text-center text-emerald-400/70">Over</div>
                  <div className="text-center">Linha</div>
                  <div className="text-center text-blue-400/70">Under</div>
                </div>
                {/* Altura fixa + rolagem vertical (mais linhas sem crescer o card) */}
                <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
                  {lines.map(L => (
                    <div key={L} className={`grid grid-cols-3 text-xs py-1.5 rounded ${L === mainLine ? 'bg-primary/10 ring-1 ring-primary/20' : 'hover:bg-muted/30'}`}>
                      <div className="text-center font-mono text-emerald-400"><Cell line={L} side="over" /></div>
                      <div className="text-center font-bold text-foreground">{L}</div>
                      <div className="text-center font-mono text-blue-400"><Cell line={L} side="under" /></div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
