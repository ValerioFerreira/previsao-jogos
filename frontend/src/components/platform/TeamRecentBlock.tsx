"use client";
import React from 'react';
import { AlertTriangle, ArrowDown, ShieldAlert, ShieldCheck, Zap } from 'lucide-react';
import { RecentMatch, Anomaly, teamLogoUrl, onImgError } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';

function formatDateBR(s: string): string {
  const d = (s || '').slice(0, 10).split('-');
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : s;
}

export function DataReliabilityBadge({ totalMatches }: { totalMatches: number }) {
  const isLow = totalMatches < 10;
  return (
    <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[10px] font-medium border ${isLow ? 'bg-amber-500/10 border-amber-500/30 text-amber-500' : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'}`}>
      {isLow ? <ShieldAlert className="w-3 h-3" /> : <ShieldCheck className="w-3 h-3" />}
      {isLow ? `Confiabilidade Baixa (${totalMatches} jogos no BD)` : `Confiabilidade Adequada (${totalMatches} jogos)`}
    </div>
  );
}

export function RecentMatchRow({ match, onOpen }: { match: RecentMatch; onOpen?: () => void }) {
  const diff = match.goals_scored - match.goals_conceded;
  const result = diff > 0 ? 'V' : diff < 0 ? 'D' : 'E';
  const color = result === 'V' ? 'bg-emerald-500/20 text-emerald-500 border-emerald-500/30' : result === 'D' ? 'bg-red-500/20 text-red-500 border-red-500/30' : 'bg-amber-500/20 text-amber-500 border-amber-500/30';
  const placar = match.is_home ? `${match.goals_scored}-${match.goals_conceded}` : `${match.goals_conceded}-${match.goals_scored}`;
  return (
    <button
      onClick={onOpen}
      className="w-full flex items-center gap-2 p-2 bg-muted/40 border border-border/50 rounded-lg text-left hover:border-cyan-500/40 hover:bg-muted/70 transition-colors cursor-pointer"
      title="Ver estatísticas deste jogo"
    >
      <span className={`flex items-center justify-center w-5 h-5 rounded-[4px] border font-bold text-[11px] shrink-0 ${color}`}>{result}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1.5">
          <span className="text-xs font-semibold truncate">
            {match.is_home ? 'Casa x ' : 'Fora x '}{teamPt(match.opponent)}
          </span>
          <span className="font-mono text-xs text-muted-foreground shrink-0">{placar}</span>
        </div>
        <p className="text-[9px] text-muted-foreground truncate">
          {formatDateBR(match.date)}{match.competition ? ` · ${competitionPt(match.competition)}` : ''}
        </p>
      </div>
      <div className="flex gap-1.5 text-[10px] text-muted-foreground shrink-0">
        <span title="Chutes">👟{match.sb_shots || 0}</span>
        <span title="Escanteios">🚩{match.sb_corners || 0}</span>
        <span title="Cartões">🟨{match.sb_cards || 0}</span>
      </div>
    </button>
  );
}

export function TeamRecentBlock({ teamId, form, anomalies, label, loading, error, teamIds, onOpenMatch }: {
  teamId: string; form: { matches: RecentMatch[]; total: number }; anomalies: Anomaly[];
  label: string; loading: boolean; error?: false | 'not_found' | 'error'; teamIds: Record<string, number>; onOpenMatch: (m: RecentMatch) => void;
}) {
  const [showMore, setShowMore] = React.useState(false);
  const totalAvailable = React.useMemo(() => Math.min(10, (form.matches || []).length), [form.matches]);
  const ms = React.useMemo(() => (form.matches || []).slice(0, showMore ? 10 : 5), [form.matches, showMore]);

  return (
    <div className="bg-card border border-border/50 rounded-xl p-4 h-full flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-center gap-2 mb-2">
          {teamLogoUrl(teamIds[teamId]) && (
            <img src={teamLogoUrl(teamIds[teamId])!} alt="" className="w-6 h-6 object-contain" loading="lazy" onError={onImgError} />
          )}
          <div className="text-center">
            <span className="text-[9px] uppercase tracking-wide text-muted-foreground block leading-none">{label}</span>
            <h3 className="text-sm font-semibold leading-tight">{teamPt(teamId)}</h3>
          </div>
        </div>
        {loading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground text-xs">
            <div className="w-4 h-4 border-2 border-muted-foreground/30 border-t-emerald-500 rounded-full animate-spin" /> Buscando…
          </div>
        ) : error === 'not_found' ? (
          <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground text-xs text-center px-2">
            <AlertTriangle className="w-4 h-4 shrink-0" /> Ainda não temos histórico coletado para esta equipe.
          </div>
        ) : error ? (
          <div className="flex items-center justify-center gap-2 py-8 text-amber-500/80 text-xs text-center px-2">
            <AlertTriangle className="w-4 h-4 shrink-0" /> Não foi possível carregar os dados. Tente novamente em instantes.
          </div>
        ) : (<>
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <p className="text-[11px] text-muted-foreground">Últimos {totalAvailable} jogos</p>
            <DataReliabilityBadge totalMatches={form.total} />
          </div>
          <div className="flex gap-2">
            {/* Seta lateral: topo = mais recente, base = mais antigo */}
            <div className="flex flex-col items-center text-[8px] uppercase text-muted-foreground shrink-0 py-0.5">
              <span>Recente</span>
              <div className="flex-1 w-px bg-border my-1" />
              <ArrowDown className="w-3 h-3" />
              <span>Antigo</span>
            </div>
            <div className="flex-1 space-y-1.5 min-w-0">
              {ms.map((m, i) => (
                <RecentMatchRow key={i} match={m} onOpen={() => onOpenMatch(m)} />
              ))}
              {ms.length === 0 && <p className="text-xs text-muted-foreground italic py-2">Sem jogos recentes.</p>}
              
              {totalAvailable > 5 && (
                <button
                  type="button"
                  onClick={() => setShowMore((prev) => !prev)}
                  className="mt-2 text-[10px] text-cyan-400 hover:text-cyan-300 font-semibold transition-colors flex items-center justify-center gap-1 mx-auto"
                >
                  {showMore ? "- Mostrar menos" : "+ Mostrar mais 5 jogos"}
                </button>
              )}
            </div>
          </div>
          <div className={`rounded-lg p-2.5 mt-3 ${anomalies.length > 0 ? 'bg-amber-500/5 border border-amber-500/20' : 'bg-muted/50 border border-border/50'}`}>
            <p className="text-[11px] font-medium mb-1 flex items-center gap-1.5">
              <Zap className={`w-3 h-3 ${anomalies.length > 0 ? 'text-amber-400' : 'text-muted-foreground'}`} /> Radar de Anomalias
            </p>
            {anomalies.length > 0 ? (
              <ul className="space-y-0.5">
                {anomalies.map((a, i) => (
                  <li key={i} className="text-[11px] text-amber-500/80 flex items-start gap-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" /><span>{a.message}</span></li>
                ))}
              </ul>
            ) : (
              <p className="text-[11px] text-muted-foreground italic">Nenhum desvio estatístico recente.</p>
            )}
          </div>
        </>)}
      </div>
    </div>
  );
}
