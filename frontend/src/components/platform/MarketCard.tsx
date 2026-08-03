"use client";
import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import InfoTooltip from './InfoTooltip';

type Distrib = { estimativa: number; distribuicao?: number[] };

type MarketCardProps = {
  title: string;
  subtitle?: string;
  prediction?: Distrib;
  periods?: Record<string, Distrib | undefined>;
  icon?: React.ReactNode;
  cardKinds?: Partial<Record<CardKind, Record<string, Distrib | undefined>>>;
  bookmakerBadge?: React.ReactNode;
};

type CardKind = 'amarelo' | 'ambos' | 'vermelho';
const CARD_KIND_ORDER: CardKind[] = ['amarelo', 'ambos', 'vermelho'];
const CARD_KIND_LABEL: Record<CardKind, string> = { amarelo: '🟨', ambos: 'Ambos', vermelho: '🟥' };
const CARD_KIND_TITLE: Record<CardKind, string> = {
  amarelo: 'Cartões amarelos',
  ambos: 'Cartões amarelos e vermelhos',
  vermelho: 'Cartões vermelhos',
};

export function fairOddRange(prob: number): string {
  if (!prob || prob <= 0) return '—';
  const odd = 1 / prob;
  if (odd > 50) return '50+';
  const hi = Math.max(1, odd);
  const lo = Math.max(1, odd * 0.93);
  return lo.toFixed(2) === hi.toFixed(2) ? hi.toFixed(2) : `${lo.toFixed(2)}–${hi.toFixed(2)}`;
}

export function overProb(dist: number[], line: number): number {
  const start = Math.floor(line) + 1;
  let s = 0;
  for (let k = start; k < dist.length; k++) s += dist[k];
  return Math.min(1, Math.max(0, s));
}

export function MarketCard({ title, subtitle, prediction, periods, icon, cardKinds, bookmakerBadge }: MarketCardProps) {
  const [viewMode, setViewMode] = useState<'prob' | 'odd'>('prob');
  const [isExpanded, setIsExpanded] = useState(false);

  const availableKinds = cardKinds ? CARD_KIND_ORDER.filter(k => cardKinds[k]) : [];
  const [kind, setKind] = useState<CardKind | ''>('');
  const effectiveKind: CardKind | '' = availableKinds.includes(kind as CardKind)
    ? (kind as CardKind)
    : (availableKinds.includes('ambos') ? 'ambos' : availableKinds[0]) ?? '';

  const effectivePeriods = cardKinds ? (effectiveKind ? cardKinds[effectiveKind] : undefined) : periods;
  const periodKeys = effectivePeriods ? Object.keys(effectivePeriods).filter(k => effectivePeriods[k]) : [];
  const [period, setPeriod] = useState<string>('');
  const effectivePeriod = periodKeys.includes(period) ? period : (periodKeys[0] ?? '');

  const active: Distrib | undefined = effectivePeriods ? effectivePeriods[effectivePeriod] : prediction;
  const dist = active?.distribuicao ?? [];
  const mean = active?.estimativa ?? 0;

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

  const mainOverP = overProb(dist, mainLine);

  return (
    <div className="bg-card border border-border/60 rounded-2xl overflow-hidden shadow-md shadow-black/10 transition-all hover:border-border/80">
      <div className="p-4 border-b border-border/40 space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider flex items-center justify-center gap-1.5 text-center text-foreground">
          {icon}
          {subtitle ?? title}
          <InfoTooltip text="Quantidade prevista é o valor esperado. A linha em destaque é a mais próxima dela." />
          {bookmakerBadge}
        </h3>
        
        <div className="flex items-center justify-between gap-2 flex-wrap text-xs">
          <div className="flex items-center gap-1.5 bg-muted/30 px-2.5 py-1 rounded-lg border border-border/40">
            <span className="text-muted-foreground text-[11px]">Projetado:</span>
            <span className="font-mono font-bold text-emerald-400">{mean.toFixed(1)}</span>
          </div>

          <div className="flex items-center gap-1.5">
            {availableKinds.length > 1 && (
              <div className="bg-muted/40 p-0.5 rounded-lg flex text-[11px] font-semibold border border-border/40">
                {availableKinds.map(k => (
                  <button
                    key={k}
                    onClick={() => setKind(k)}
                    title={CARD_KIND_TITLE[k]}
                    className={`px-2 py-0.5 rounded-md transition-all ${effectiveKind === k ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                  >{CARD_KIND_LABEL[k]}</button>
                ))}
              </div>
            )}
            <div className="bg-muted/40 p-0.5 rounded-lg flex text-[11px] font-semibold border border-border/40">
              <button
                onClick={() => setViewMode('prob')}
                className={`px-2.5 py-0.5 rounded-md transition-all ${viewMode === 'prob' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              >Prob.</button>
              <button
                onClick={() => setViewMode('odd')}
                className={`px-2.5 py-0.5 rounded-md transition-all ${viewMode === 'odd' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              >Odd</button>
            </div>
          </div>
        </div>
      </div>

      {periodKeys.length > 1 && (
        <div className="px-4 pt-3 flex gap-1.5 flex-wrap">
          {periodKeys.map(k => (
            <button
              key={k}
              onClick={() => setPeriod(k)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-semibold border transition-all ${period === k ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' : 'border-border/40 text-muted-foreground hover:text-foreground'}`}
            >{k}</button>
          ))}
        </div>
      )}

      <div className="p-4 space-y-3">
        {/* Banner da linha principal */}
        <div className="bg-muted/20 p-3 rounded-xl border border-border/50 space-y-2">
          <div className="flex justify-between items-center text-xs">
            <div className="flex-1 text-center">
              <span className="block text-[11px] text-muted-foreground mb-0.5">Acima de {mainLine}</span>
              <span className="font-mono font-bold text-base text-emerald-400"><Cell line={mainLine} side="over" /></span>
            </div>
            <div className="w-px h-8 bg-border/40" />
            <div className="flex-1 text-center">
              <span className="block text-[11px] text-muted-foreground mb-0.5">Abaixo de {mainLine}</span>
              <span className="font-mono font-bold text-base text-cyan-400"><Cell line={mainLine} side="under" /></span>
            </div>
          </div>

          {/* Probability relative progress bar */}
          <div className="w-full bg-cyan-950/40 h-1.5 rounded-full overflow-hidden flex border border-white/5">
            <div className="bg-emerald-500 transition-all duration-300" style={{ width: `${mainOverP * 100}%` }} />
            <div className="bg-cyan-500 transition-all duration-300" style={{ width: `${(1 - mainOverP) * 100}%` }} />
          </div>
        </div>

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-center gap-1.5 py-1.5 text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? 'Ocultar Linhas Alternativas' : 'Ver Linhas Alternativas'}
          <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
        </button>

        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="pt-2 border-t border-border/40 space-y-1">
                <div className="grid grid-cols-3 text-[10px] font-mono font-bold text-muted-foreground uppercase text-center pb-1">
                  <span className="text-emerald-400">Acima</span>
                  <span>Linha</span>
                  <span className="text-cyan-400">Abaixo</span>
                </div>
                <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                  {lines.map(L => (
                    <div key={L} className={`grid grid-cols-3 text-xs py-1.5 rounded-lg border transition-colors ${L === mainLine ? 'bg-emerald-500/10 border-emerald-500/30' : 'border-transparent hover:bg-muted/30'}`}>
                      <div className="text-center font-mono font-semibold text-emerald-400"><Cell line={L} side="over" /></div>
                      <div className="text-center font-mono font-bold text-foreground">{L}</div>
                      <div className="text-center font-mono font-semibold text-cyan-400"><Cell line={L} side="under" /></div>
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

