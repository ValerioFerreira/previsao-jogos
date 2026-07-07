"use client";
import React from "react";
import { ScorersResponse, ScorerPlayer, teamLogoUrl, playerPhotoUrl } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

const hideOnError = (e: React.SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.display = "none"; };

function top(players?: ScorerPlayer[]): ScorerPlayer | null {
  if (!players || players.length === 0) return null;
  return players.reduce((a, b) => (b.prob > a.prob ? b : a));
}

function PlayerSide({ team, p, teamIds, accent, align }: {
  team: string; p: ScorerPlayer; teamIds: Record<string, number>; accent: string; align: "left" | "right";
}) {
  return (
    <div className={`flex-1 flex flex-col items-center text-center ${align === "right" ? "sm:items-end sm:text-right" : "sm:items-start sm:text-left"}`}>
      <div className="relative">
        <div className="w-20 h-20 rounded-full bg-muted overflow-hidden ring-2" style={{ ["--tw-ring-color" as any]: accent }}>
          {playerPhotoUrl(p.player_id)
            ? <img src={playerPhotoUrl(p.player_id)!} alt="" className="w-full h-full object-cover" loading="lazy" onError={hideOnError} />
            : <span className="flex items-center justify-center w-full h-full text-xl font-bold text-muted-foreground">{(p.nome || "?")[0]}</span>}
        </div>
        {teamLogoUrl(teamIds[team]) && <img src={teamLogoUrl(teamIds[team])!} alt="" className="absolute -bottom-1 -right-1 w-7 h-7 object-contain bg-background rounded-full p-0.5" onError={hideOnError} />}
      </div>
      <p className="text-sm font-semibold mt-2 leading-tight">{p.nome}</p>
      <p className="text-[11px] text-muted-foreground">{teamPt(team)}{p.pos ? ` · ${p.pos}` : ""}</p>
      <p className="text-2xl font-bold font-mono mt-1" style={{ color: accent }}>{p.prob.toFixed(1)}%</p>
      <p className="text-[10px] text-muted-foreground">chance de marcar · odd justa {p.odd_justa.toFixed(2)}</p>
    </div>
  );
}

export default function KeyPlayerMatchup({ data, home, away, teamIds }: {
  data: ScorersResponse | null; home: string; away: string; teamIds: Record<string, number>;
}) {
  if (!data?.disponivel) return null;
  const hp = top(data[home] as ScorerPlayer[] | undefined);
  const ap = top(data[away] as ScorerPlayer[] | undefined);
  if (!hp && !ap) return null;

  const total = (hp?.prob || 0) + (ap?.prob || 0);
  const hPct = total > 0 ? ((hp?.prob || 0) / total) * 100 : 50;

  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Duelo de Estrelas
        <InfoTooltip text="O jogador mais provável de marcar de cada seleção, frente a frente (modelo de goleador: forma recente + defesa do adversário + mando). Odd justa = 1/probabilidade, sem margem." />
      </h3>
      <p className="text-xs text-muted-foreground mb-4">Maior probabilidade de marcar em cada equipe</p>
      <div className="flex items-start gap-3">
        {hp ? <PlayerSide team={home} p={hp} teamIds={teamIds} accent="#10b981" align="left" />
          : <div className="flex-1 text-center text-xs text-muted-foreground italic">sem dados</div>}
        <div className="shrink-0 self-center px-1">
          <span className="text-muted-foreground font-bold font-mono text-lg">VS</span>
        </div>
        {ap ? <PlayerSide team={away} p={ap} teamIds={teamIds} accent="#f97316" align="right" />
          : <div className="flex-1 text-center text-xs text-muted-foreground italic">sem dados</div>}
      </div>
      {hp && ap && (
        <div className="mt-4">
          <div className="h-2 rounded-full overflow-hidden flex">
            <div style={{ width: `${hPct}%`, backgroundColor: "#10b981" }} />
            <div style={{ width: `${100 - hPct}%`, backgroundColor: "#f97316" }} />
          </div>
          <p className="text-[11px] text-center text-muted-foreground mt-1.5">
            {hp.prob >= ap.prob
              ? <><b className="text-emerald-400">{hp.nome}</b> é o mais provável a balançar as redes</>
              : <><b className="text-orange-400">{ap.nome}</b> é o mais provável a balançar as redes</>}
          </p>
        </div>
      )}
    </div>
  );
}
