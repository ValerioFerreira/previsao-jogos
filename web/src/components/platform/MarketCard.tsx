"use client";
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { CountPrediction, OverUnderLine } from '@/lib/api';
import InfoTooltip from './InfoTooltip';

type MarketCardProps = {
  title: string;
  subtitle?: string;
  prediction: CountPrediction;
  icon?: React.ReactNode;
};

export function MarketCard({ title, subtitle, prediction, icon }: MarketCardProps) {
  const [viewMode, setViewMode] = useState<'prob' | 'odd'>('odd');
  const [isExpanded, setIsExpanded] = useState(false);

  // We sort the keys to display lines sequentially
  const lines = Object.entries(prediction.linhas).sort(([a], [b]) => parseFloat(a) - parseFloat(b));
  
  if (lines.length === 0) return null;

  // Most balanced line (closest to 50% / 2.00 odd) to show when collapsed
  let mainLineKey = lines[0][0];
  let minDiff = 100;
  for (const [lineKey, lineData] of lines) {
    const diff = Math.abs(lineData.over.prob - 0.5);
    if (diff < minDiff) {
      minDiff = diff;
      mainLineKey = lineKey;
    }
  }

  const mainLine = prediction.linhas[mainLineKey];

  return (
    <div className="bg-card border border-border/50 rounded-xl overflow-hidden">
      <div className="p-4 border-b border-border/30 flex justify-between items-start">
        <div>
          <h3 className="text-sm font-semibold flex items-center gap-1.5">
            {icon}
            {title}
            <InfoTooltip text="Média projetada é o Valor Esperado (EV) estatístico. A linha principal é a mais próxima de 50/50." />
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            Média Projetada: <span className="font-bold text-foreground">{prediction.estimativa}</span> 
            {subtitle && <span> • {subtitle}</span>}
          </p>
        </div>
        <div className="bg-muted p-1 rounded-md flex text-[10px] font-medium">
          <button 
            onClick={() => setViewMode('prob')}
            className={`px-2 py-1 rounded transition-colors ${viewMode === 'prob' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            Prob.
          </button>
          <button 
            onClick={() => setViewMode('odd')}
            className={`px-2 py-1 rounded transition-colors ${viewMode === 'odd' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            Odd
          </button>
        </div>
      </div>

      <div className="p-4">
        {/* Main Line Banner */}
        <div className="flex justify-between items-center mb-3 text-xs bg-muted/40 p-3 rounded-lg border border-border/40">
          <div className="flex-1 text-center">
            <span className="block text-muted-foreground mb-1">Over {mainLineKey}</span>
            <span className="font-mono font-bold text-emerald-400">
              {viewMode === 'prob' ? `${(mainLine.over.prob * 100).toFixed(1)}%` : mainLine.over.odd_justa > 50 ? '50+' : mainLine.over.odd_justa}
            </span>
          </div>
          <div className="flex-1 text-center border-l border-border/40">
            <span className="block text-muted-foreground mb-1">Under {mainLineKey}</span>
            <span className="font-mono font-bold text-blue-400">
              {viewMode === 'prob' ? `${(mainLine.under.prob * 100).toFixed(1)}%` : mainLine.under.odd_justa > 50 ? '50+' : mainLine.under.odd_justa}
            </span>
          </div>
        </div>

        {/* Accordion Toggle */}
        <button 
          onClick={() => setIsExpanded(!isExpanded)}
          className="w-full flex items-center justify-center gap-1 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          {isExpanded ? 'Ocultar Linhas Alternativas' : 'Ver Todas as Linhas'}
          <ChevronDown className={`w-3 h-3 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`} />
        </button>

        {/* Expanded Table */}
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
                <div className="space-y-1">
                  {lines.map(([key, data]) => (
                    <div key={key} className={`grid grid-cols-3 text-xs py-1.5 rounded ${key === mainLineKey ? 'bg-primary/5' : 'hover:bg-muted/30'}`}>
                      <div className="text-center font-mono text-emerald-400">
                        {viewMode === 'prob' ? `${(data.over.prob * 100).toFixed(1)}%` : data.over.odd_justa > 50 ? '50+' : data.over.odd_justa}
                      </div>
                      <div className="text-center font-bold text-foreground">{key}</div>
                      <div className="text-center font-mono text-blue-400">
                        {viewMode === 'prob' ? `${(data.under.prob * 100).toFixed(1)}%` : data.under.odd_justa > 50 ? '50+' : data.under.odd_justa}
                      </div>
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
