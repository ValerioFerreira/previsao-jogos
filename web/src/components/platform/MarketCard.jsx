import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import InfoTooltip from './InfoTooltip';
import { getOddFromProb, getProbFromOdd, calculateOverProb, calculateUnderProb } from '@/lib/mock-data';

export default function MarketCard({ market, index }) {
  const [mode, setMode] = useState('prob'); // 'prob' or 'odd'
  const [side, setSide] = useState('over');
  const [targetLine, setTargetLine] = useState(Math.round(market.mean - 0.5) + 0.5);
  const [customOdd, setCustomOdd] = useState('');

  const prob = side === 'over'
    ? calculateOverProb(market.distribution, targetLine)
    : calculateUnderProb(market.distribution, targetLine);

  const fairOdd = getOddFromProb(prob);

  useEffect(() => {
    if (mode === 'odd' && customOdd) {
      const oddVal = parseFloat(customOdd);
      if (oddVal > 1) {
        // Find closest line that matches this odd
      }
    }
  }, [customOdd, mode]);

  const minLine = Math.max(0, Math.floor(market.mean) - 4) + 0.5;
  const maxLine = Math.floor(market.mean) + 5 + 0.5;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.4 }}
      className="bg-card border border-border/50 rounded-xl p-5 hover:border-border transition-colors"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-foreground">{market.label}</h3>
          <InfoTooltip text={`Projeção baseada na distribuição de probabilidade (PMF/CDF) calculada a partir do modelo preditivo para ${market.label.toLowerCase()}.`} />
        </div>
        <div className="text-2xl font-bold font-mono text-foreground">
          {market.mean}
        </div>
      </div>

      {/* Side Toggle */}
      <div className="flex gap-1 mb-4">
        <button
          onClick={() => setSide('over')}
          className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${
            side === 'over' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-muted text-muted-foreground'
          }`}
        >
          Over
        </button>
        <button
          onClick={() => setSide('under')}
          className={`flex-1 py-1.5 text-xs font-medium rounded-md transition-colors ${
            side === 'under' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-muted text-muted-foreground'
          }`}
        >
          Under
        </button>
      </div>

      {/* Mode Toggle */}
      <div className="flex gap-1 mb-3 bg-muted rounded-lg p-0.5">
        <button
          onClick={() => setMode('prob')}
          className={`flex-1 py-1 text-[10px] font-medium rounded-md transition-colors ${
            mode === 'prob' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
          }`}
        >
          Probabilidade
        </button>
        <button
          onClick={() => setMode('odd')}
          className={`flex-1 py-1 text-[10px] font-medium rounded-md transition-colors ${
            mode === 'odd' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground'
          }`}
        >
          Odd
        </button>
      </div>

      {mode === 'prob' ? (
        <div>
          <div className="mb-2">
            <Slider
              value={[targetLine]}
              onValueChange={([v]) => setTargetLine(v)}
              min={minLine}
              max={maxLine}
              step={0.5}
              className="w-full"
            />
          </div>
          <div className="flex justify-between items-center text-xs mt-3">
            <span className="text-muted-foreground">
              Linha: <span className="text-foreground font-mono font-semibold">{side === 'over' ? 'Over' : 'Under'} {targetLine}</span>
            </span>
            <div className="flex items-center gap-3">
              <span className="text-muted-foreground">
                Prob: <span className="text-foreground font-mono font-semibold">{(prob * 100).toFixed(1)}%</span>
              </span>
              <span className="text-muted-foreground">
                Odd Justa: <span className="font-mono font-bold text-emerald-400">{fairOdd > 50 ? '50+' : fairOdd}</span>
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div>
          <Input
            type="number"
            step="0.01"
            min="1.01"
            placeholder="Digite a odd de referência..."
            value={customOdd}
            onChange={e => setCustomOdd(e.target.value)}
            className="text-sm font-mono mb-3 h-9"
          />
          {customOdd && parseFloat(customOdd) > 1 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex justify-between items-center text-xs"
            >
              <span className="text-muted-foreground">
                Prob. Implícita: <span className="text-foreground font-mono font-semibold">{(getProbFromOdd(parseFloat(customOdd)) * 100).toFixed(1)}%</span>
              </span>
              <span className="text-muted-foreground">
                Prob. Modelo ({side === 'over' ? 'Over' : 'Under'} {targetLine}): <span className="font-mono font-bold text-cyan-400">{(prob * 100).toFixed(1)}%</span>
              </span>
            </motion.div>
          )}
        </div>
      )}
    </motion.div>
  );
}