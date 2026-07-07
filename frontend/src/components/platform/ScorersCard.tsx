"use client";
import React from "react";
import { ScorersResponse, ScorerPlayer, teamLogoUrl, playerPhotoUrl } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

const hideOnError = (e: React.SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.display = "none"; };

function Column({ team, players, teamIds }: { team: string; players: ScorerPlayer[]; teamIds: Record<string, number> }) {
  if (!players || players.length === 0) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-4">
      <div className="flex items-center justify-center gap-2 mb-2">
        {teamLogoUrl(teamIds[team]) && <img src={teamLogoUrl(teamIds[team])!} alt="" className="w-6 h-6 object-contain" loading="lazy" onError={hideOnError} />}
        <h4 className="text-sm font-semibold">{teamPt(team)}</h4>
      </div>
      {/* Cabeçalho das colunas */}
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground pb-1 border-b border-border/30">
        <span className="w-6 shrink-0" />
        <span className="flex-1">Jogador</span>
        <span className="shrink-0 w-12 text-right">Prob.</span>
        <span className="shrink-0 w-14 text-right">Odd justa</span>
      </div>
      {/* Lista rolável (altura reduzida) */}
      <div className="max-h-56 overflow-y-auto pr-1 mt-1">
        {players.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs py-1 border-t border-border/15 first:border-t-0">
            {playerPhotoUrl(p.player_id)
              ? <img src={playerPhotoUrl(p.player_id)!} alt="" className="w-6 h-6 rounded-full object-cover bg-muted shrink-0" loading="lazy" onError={hideOnError} />
              : <span className="w-6 h-6 rounded-full bg-muted shrink-0" />}
            <span className="flex-1 truncate">
              <span className="font-medium">{p.nome}</span>
              {p.pos && <span className="text-muted-foreground ml-1 text-[10px]">{p.pos}</span>}
            </span>
            <span className="font-mono font-bold text-emerald-400 shrink-0 w-12 text-right">{p.prob.toFixed(1)}%</span>
            <span className="font-mono text-[10px] text-muted-foreground shrink-0 w-14 text-right">{p.odd_justa.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ScorersCard({ data, home, away, teamIds }: {
  data: ScorersResponse; home: string; away: string; teamIds: Record<string, number>;
}) {
  if (!data?.disponivel) return null;
  const hp = data[home] as ScorerPlayer[] | undefined;
  const ap = data[away] as ScorerPlayer[] | undefined;
  if ((!hp || hp.length === 0) && (!ap || ap.length === 0)) return null;
  return (
    <div className="mt-8">
      <h4 className="text-sm font-bold uppercase text-foreground mb-4 flex items-center justify-center gap-1.5">
        Jogador a Marcar
        <InfoTooltip text="Probabilidade de cada jogador marcar a qualquer momento, se jogar (modelo de goleador: forma recente + defesa do adversário + mando). Candidatos = elenco recente da seleção; refina com a escalação confirmada. Odd justa = 1/probabilidade, sem margem de casa." />
      </h4>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Column team={home} players={hp || []} teamIds={teamIds} />
        <Column team={away} players={ap || []} teamIds={teamIds} />
      </div>
    </div>
  );
}
