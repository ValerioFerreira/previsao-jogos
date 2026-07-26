"use client";
import React, { useMemo } from "react";
import { Swords } from "lucide-react";
import type { RecentMatch } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import { summarize, TeamStatSummary, getRelevantMatches } from "@/lib/teamInsights";
import InfoTooltip from "@/components/platform/InfoTooltip";

export default function StyleMatchup({ home, away, homeMatches, awayMatches, targetCompetition }: {
  home: string; away: string; homeMatches: RecentMatch[]; awayMatches: RecentMatch[];
  targetCompetition?: string;
}) {
  const homeMatches10 = useMemo(() => getRelevantMatches(homeMatches || [], targetCompetition, 10), [homeMatches, targetCompetition]);
  const awayMatches10 = useMemo(() => getRelevantMatches(awayMatches || [], targetCompetition, 10), [awayMatches, targetCompetition]);

  const hs = useMemo(() => summarize(homeMatches10), [homeMatches10]);
  const as = useMemo(() => summarize(awayMatches10), [awayMatches10]);
  
  if (hs.n === 0 && as.n === 0) return null;

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5 h-full flex flex-col justify-between">
      <div>
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
          <Swords className="w-4 h-4 text-violet-500" />
          Confronto de Estilos (Gols/Jogo)
          <InfoTooltip text="Média de gols marcados (Ataque) e gols sofridos (Defesa) por jogo nas 10 partidas mais relevantes recentes." />
        </h3>
        
        <div className="grid grid-cols-3 gap-2.5 text-center text-xs mt-3">
          {/* Header Row */}
          <div className="text-left font-semibold text-muted-foreground flex items-center">Equipe</div>
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 font-bold border border-emerald-500/15">Ataque</div>
          <div className="p-2 rounded-lg bg-orange-500/10 text-orange-400 font-bold border border-orange-500/15">Defesa</div>
          
          {/* Row 1: Home */}
          <div className="text-left font-bold flex items-center truncate text-[11.5px] py-1 text-[#52F4E3]">{teamPt(home)}</div>
          <div className="p-4 rounded-xl bg-muted/30 font-mono text-base font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm hover:bg-muted/40 transition-colors">
            <span className="text-lg text-[#52F4E3]">{hs.avgGoalsScored.toFixed(2)}</span>
            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Marcados</span>
          </div>
          <div className="p-4 rounded-xl bg-muted/30 font-mono text-base font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm hover:bg-muted/40 transition-colors">
            <span className="text-lg text-[#52F4E3]/80">{hs.avgGoalsConceded.toFixed(2)}</span>
            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Sofridos</span>
          </div>
          
          {/* Row 2: Away */}
          <div className="text-left font-bold flex items-center truncate text-[11.5px] py-1 text-[#F97316]">{teamPt(away)}</div>
          <div className="p-4 rounded-xl bg-muted/30 font-mono text-base font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm hover:bg-muted/40 transition-colors">
            <span className="text-lg text-[#F97316]">{as.avgGoalsScored.toFixed(2)}</span>
            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Marcados</span>
          </div>
          <div className="p-4 rounded-xl bg-muted/30 font-mono text-base font-bold flex flex-col items-center justify-center border border-border/20 shadow-sm hover:bg-muted/40 transition-colors">
            <span className="text-lg text-[#F97316]/80">{as.avgGoalsConceded.toFixed(2)}</span>
            <span className="text-[8px] text-muted-foreground mt-0.5 uppercase tracking-wider">Sofridos</span>
          </div>
        </div>
      </div>
      
      <p className="text-[9.5px] text-muted-foreground leading-normal mt-4 pt-3 border-t border-border/25">
        * Quanto maior o valor de Ataque, mais gols a equipe marca por jogo. Quanto menor o valor de defesa, menos gols a equipe sofre por jogo.
      </p>
    </div>
  );
}
