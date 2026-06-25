import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import InfoTooltip from './InfoTooltip';

const RESULT_COLORS = {
  V: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
  E: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  D: 'bg-red-500/20 text-red-400 border-red-500/30',
};

const RESULT_LABELS = { V: 'Vitória', E: 'Empate', D: 'Derrota' };

export default function FormBadge({ match }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`inline-flex flex-col items-center px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all hover:scale-105 ${RESULT_COLORS[match.result]}`}
      >
        <span className="font-bold text-[10px]">{RESULT_LABELS[match.result]}</span>
        <span className="font-mono text-xs">{match.score}</span>
        <span className="text-[9px] opacity-70 truncate max-w-[60px]">vs {match.opponent}</span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="absolute top-full mt-1 left-1/2 -translate-x-1/2 z-30 bg-popover border border-border rounded-lg p-3 shadow-xl min-w-[160px]"
          >
            <p className="text-xs font-semibold mb-2 text-foreground">vs {match.opponent} ({match.score})</p>
            <div className="grid grid-cols-2 gap-1.5 text-[10px] text-muted-foreground">
              <span>Gols Pró:</span><span className="text-foreground font-medium">{match.stats.golsPro}</span>
              <span>Gols Contra:</span><span className="text-foreground font-medium">{match.stats.golsContra}</span>
              <span>Chutes:</span><span className="text-foreground font-medium">{match.stats.chutes}</span>
              <span>No Alvo:</span><span className="text-foreground font-medium">{match.stats.chutesNoAlvo}</span>
              <span>Escanteios:</span><span className="text-foreground font-medium">{match.stats.escanteios}</span>
              <span>Cartões:</span><span className="text-foreground font-medium">{match.stats.cartoes}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}