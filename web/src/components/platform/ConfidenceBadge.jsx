import React from 'react';
import InfoTooltip from './InfoTooltip';

export default function ConfidenceBadge({ totalGames }) {
  let color, label;
  if (totalGames >= 20) {
    color = 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30';
    label = '🟢 Confiabilidade Alta';
  } else if (totalGames >= 10) {
    color = 'bg-amber-500/15 text-amber-400 border-amber-500/30';
    label = '🟡 Confiabilidade Média';
  } else {
    color = 'bg-red-500/15 text-red-400 border-red-500/30';
    label = '🔴 Confiabilidade Frágil';
  }

  return (
    <div className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-xs font-medium ${color}`}>
      <span>{label}</span>
      <span className="opacity-60">({totalGames} jogos)</span>
      <InfoTooltip text="O nível de confiabilidade reflete a densidade amostral disponível para calibrar o modelo. Quanto maior o histórico de confrontos, mais robusta é a previsão estatística." />
    </div>
  );
}