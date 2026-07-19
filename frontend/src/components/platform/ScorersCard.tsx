"use client";
import { ScorersResponse, ScorerPlayer, teamLogoUrl, playerPhotoUrl, onImgError as hideOnError } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

const FIN_LINES = ["0.5", "1.5", "2.5"];

function Column({ team, players, teamIds, showFin, showAst }: { team: string; players: ScorerPlayer[]; teamIds: Record<string, number>; showFin: boolean; showAst: boolean }) {
  if (!players || players.length === 0) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-4">
      <div className="flex items-center justify-center gap-2 mb-2">
        {teamLogoUrl(teamIds[team]) && <img src={teamLogoUrl(teamIds[team])!} alt="" className="w-6 h-6 object-contain" loading="lazy" onError={hideOnError} />}
        <h4 className="text-sm font-semibold">{teamPt(team)}</h4>
      </div>
      {/* Cabeçalho de grupos: Marcar | Assistir | Finalizar (≥) — separação visual */}
      {(showFin || showAst) && (
        <div className="flex items-end gap-2 text-[9px] uppercase tracking-wide text-muted-foreground/80">
          <span className="w-6 shrink-0" />
          <span className="flex-1" />
          <span className="w-12 text-center text-emerald-400/80 font-semibold">Marcar</span>
          {showAst && <span className="shrink-0 border-l border-border/40 pl-2 text-center text-amber-400/80 font-semibold w-12">Assistir</span>}
          {showFin && <span className="shrink-0 border-l border-border/40 pl-2 text-center text-cyan-400/80 font-semibold" style={{ width: "8.25rem" }}>Finalizar (≥)</span>}
        </div>
      )}
      {/* Cabeçalho das colunas */}
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide text-muted-foreground pb-1 border-b border-border/30">
        <span className="w-6 shrink-0" />
        <span className="flex-1">Jogador</span>
        <span className="shrink-0 w-12 text-right">Prob.</span>
        {showAst && <span className="shrink-0 w-12 text-right border-l border-border/40 pl-2">Prob.</span>}
        {showFin ? (
          <span className="shrink-0 flex border-l border-border/40 pl-2 gap-1">
            {FIN_LINES.map((l) => <span key={l} className="w-11 text-right">{l.replace(".", ",")}</span>)}
          </span>
        ) : (
          <span className="shrink-0 w-14 text-right">Odd justa</span>
        )}
      </div>
      {/* Lista rolável */}
      <div className="max-h-72 overflow-y-auto pr-1 mt-1">
        {players.map((p, i) => (
          <div key={i} className="flex items-center gap-2 text-xs py-1 border-t border-border/15 first:border-t-0">
            {playerPhotoUrl(p.player_id)
              ? <img src={playerPhotoUrl(p.player_id)!} alt="" className="w-6 h-6 rounded-full object-cover bg-muted shrink-0" loading="lazy" onError={hideOnError} />
              : <span className="w-6 h-6 rounded-full bg-muted shrink-0" />}
            <span className="flex-1 truncate">
              <span className="font-medium">{p.nome}</span>
              {p.pos && <span className="text-muted-foreground ml-1 text-[10px]">{p.pos}</span>}
            </span>
            <span className="font-mono font-bold text-emerald-400 shrink-0 w-12 text-right" title={`Marcar · odd justa ${p.odd_justa.toFixed(2)}`}>{p.prob.toFixed(1)}%</span>
            {showAst && (
              <span className="font-mono font-bold text-amber-400 shrink-0 w-12 text-right border-l border-border/40 pl-2" title={p.assistir ? `Assistir · odd justa ${p.assistir.odd_justa.toFixed(2)}` : ""}>
                {p.assistir ? `${p.assistir.prob.toFixed(1)}%` : "—"}
              </span>
            )}
            {showFin ? (
              <span className="shrink-0 flex border-l border-border/40 pl-2 gap-1">
                {FIN_LINES.map((l) => {
                  const f = p.finalizar?.[l];
                  return (
                    <span key={l} className="w-11 text-right font-mono text-cyan-400" title={f ? `Finalizações ≥ ${l.replace(".", ",")} · odd justa ${f.odd_justa.toFixed(2)}` : ""}>
                      {f ? `${f.prob.toFixed(0)}%` : "—"}
                    </span>
                  );
                })}
              </span>
            ) : (
              <span className="font-mono text-[10px] text-muted-foreground shrink-0 w-14 text-right">{p.odd_justa.toFixed(2)}</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ScorersCard({ data, home, away, teamIds, embedded = false }: {
  data: ScorersResponse; home: string; away: string; teamIds: Record<string, number>; embedded?: boolean;
}) {
  if (!data?.disponivel) return null;
  const hp = data[home] as ScorerPlayer[] | undefined;
  const ap = data[away] as ScorerPlayer[] | undefined;
  if ((!hp || hp.length === 0) && (!ap || ap.length === 0)) return null;
  const showFin = data.finalizar_disponivel === true;
  const showAst = data.assistir_disponivel === true;
  const grid = (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <Column team={home} players={hp || []} teamIds={teamIds} showFin={showFin} showAst={showAst} />
      <Column team={away} players={ap || []} teamIds={teamIds} showFin={showFin} showAst={showAst} />
    </div>
  );
  // Embutido numa subseção colapsável (que já mostra o título) — sem cabeçalho próprio.
  if (embedded) return grid;
  return (
    <div className="mt-8">
      <h4 className="text-sm font-bold uppercase text-foreground mb-4 flex items-center justify-center gap-1.5">
        Jogador
        <InfoTooltip text="Por jogador do elenco recente, se jogar: P(marcar a qualquer momento), P(dar assistência) e P(finalizações ≥ 0,5/1,5/2,5) — modelos de goleador, assistência e finalizações (forma + defesa do adversário + mando + minutos), calibrados. Odd justa = 1/probabilidade, sem margem de casa." />
      </h4>
      {grid}
    </div>
  );
}
