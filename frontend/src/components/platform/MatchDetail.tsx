"use client";
import React from 'react';
import { MatchDetail as MD, teamLogoUrl, playerPhotoUrl } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';

function dBR(s?: string | null): string {
  const d = (s || '').slice(0, 10).split('-');
  return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : (s || '');
}

const STAT_ROWS: [string, string][] = [
  ['Ball Possession', 'Posse de bola'],
  ['expected_goals', 'Gols esperados (xG)'],
  ['Total Shots', 'Finalizações'],
  ['Shots on Goal', 'Chutes a gol'],
  ['Shots off Goal', 'Chutes para fora'],
  ['Blocked Shots', 'Chutes bloqueados'],
  ['Shots insidebox', 'Chutes na área'],
  ['Shots outsidebox', 'Chutes fora da área'],
  ['Corner Kicks', 'Escanteios'],
  ['Fouls', 'Faltas'],
  ['Offsides', 'Impedimentos'],
  ['Yellow Cards', 'Cartões amarelos'],
  ['Red Cards', 'Cartões vermelhos'],
  ['Goalkeeper Saves', 'Defesas do goleiro'],
  ['Total passes', 'Passes'],
  ['Passes %', 'Precisão de passe'],
];

function eventIcon(type: string, detail: string): string {
  const t = (type || '').toLowerCase();
  if (t === 'goal') return detail?.includes('Own') ? '🥅' : (detail?.includes('Penalty') ? '⚽(P)' : '⚽');
  if (t === 'card') return detail?.includes('Red') ? '🟥' : '🟨';
  if (t === 'subst') return '🔄';
  if (t === 'var') return '📺';
  return '•';
}

const hideOnError = (e: React.SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.display = 'none'; };

const Logo = ({ id, size = 24 }: { id?: number | null; size?: number }) => {
  const url = teamLogoUrl(id ?? undefined);
  return url ? <img src={url} alt="" width={size} height={size} className="object-contain inline-block" loading="lazy" onError={hideOnError} /> : null;
};

export function MatchDetail({ data }: { data: MD }) {
  if (!data?.found || !data.info) {
    return (
      <div className="text-center py-16 text-muted-foreground text-sm">
        Detalhe desta partida não está disponível no histórico local.
      </div>
    );
  }
  const info = data.info;
  const g = data.goals || { home: null, away: null };
  const ht = data.score?.halftime;
  const statByTeam = (data.statistics || []);
  const homeStats = statByTeam.find(s => s.team_id === info.home_id)?.stats || statByTeam[0]?.stats || {};
  const awayStats = statByTeam.find(s => s.team_id === info.away_id)?.stats || statByTeam[1]?.stats || {};

  return (
    <div className="space-y-6">
      {/* Cabeçalho */}
      <div className="bg-card border border-border/50 rounded-xl p-6">
        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground mb-4">
          {info.league_logo && <img src={info.league_logo} alt="" className="w-4 h-4 object-contain" onError={hideOnError} />}
          <span>{competitionPt(info.league)}{info.round ? ` · ${info.round}` : ''} · {dBR(info.date)}</span>
        </div>
        <div className="flex items-center justify-center gap-4 sm:gap-8">
          <div className="text-center flex-1">
            <Logo id={info.home_id} size={48} />
            <p className="font-semibold mt-1 text-sm">{teamPt(info.home || '')}</p>
          </div>
          <div className="text-center shrink-0">
            <p className="text-3xl font-bold font-mono">{g.home ?? '-'} <span className="text-muted-foreground">x</span> {g.away ?? '-'}</p>
            {ht && ht.home != null && <p className="text-[10px] text-muted-foreground mt-1">1º tempo: {ht.home}-{ht.away}</p>}
            <p className="text-[10px] text-muted-foreground mt-1">{info.status}</p>
          </div>
          <div className="text-center flex-1">
            <Logo id={info.away_id} size={48} />
            <p className="font-semibold mt-1 text-sm">{teamPt(info.away || '')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground mt-4 border-t border-border/30 pt-3">
          {info.venue && <span>🏟️ {info.venue}{info.city ? `, ${info.city}` : ''}</span>}
          {info.referee && <span>👨‍⚖️ {info.referee}</span>}
        </div>
      </div>

      {/* Estatísticas */}
      {statByTeam.length > 0 && (
        <div className="bg-card border border-border/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">Estatísticas da Partida</h3>
          <div className="space-y-2">
            {STAT_ROWS.filter(([k]) => homeStats[k] != null || awayStats[k] != null).map(([k, label]) => (
              <div key={k} className="grid grid-cols-3 items-center text-xs">
                <span className="font-mono font-semibold text-left text-emerald-400">{homeStats[k] ?? '-'}</span>
                <span className="text-center text-muted-foreground">{label}</span>
                <span className="font-mono font-semibold text-right text-cyan-400">{awayStats[k] ?? '-'}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Linha do tempo de eventos */}
      {(data.events || []).length > 0 && (
        <div className="bg-card border border-border/50 rounded-xl p-5">
          <h3 className="text-sm font-semibold mb-4">Linha do Tempo</h3>
          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
            {data.events!.map((e, i) => {
              const isHome = e.team === info.home;
              return (
                <div key={i} className={`flex items-center gap-2 text-xs ${isHome ? 'flex-row' : 'flex-row-reverse text-right'}`}>
                  <span className="font-mono text-muted-foreground w-9 shrink-0">{e.minute}'{e.extra ? `+${e.extra}` : ''}</span>
                  <span className="shrink-0">{eventIcon(e.type, e.detail)}</span>
                  <span className="truncate">
                    <span className="font-medium">{e.player}</span>
                    {e.assist && <span className="text-muted-foreground"> ({e.detail === 'Substitution' ? 'entra' : 'assist'}: {e.assist})</span>}
                    {e.type === 'Card' && <span className="text-muted-foreground"> · {e.detail}</span>}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Escalações */}
      {(data.lineups || []).length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data.lineups!.map((lu, idx) => (
            <div key={idx} className="bg-card border border-border/50 rounded-xl p-5">
              <div className="flex items-center gap-2 mb-1">
                <Logo id={lu.team_id} size={20} />
                <h3 className="text-sm font-semibold">{teamPt(lu.team || '')}</h3>
                {lu.formation && <span className="text-[10px] text-muted-foreground ml-auto font-mono">{lu.formation}</span>}
              </div>
              {lu.coach?.name && <p className="text-[11px] text-muted-foreground mb-3">Técnico: {lu.coach.name}</p>}
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">Titulares</p>
              <div className="grid grid-cols-2 gap-1.5 mb-3">
                {lu.startXI.map((p, i) => (
                  <div key={i} className="flex items-center gap-1.5 text-xs">
                    {playerPhotoUrl(p.id) && <img src={playerPhotoUrl(p.id)!} alt="" className="w-6 h-6 rounded-full object-cover bg-muted" loading="lazy" onError={hideOnError} />}
                    <span className="truncate">{p.number ? `${p.number}. ` : ''}{p.name}</span>
                  </div>
                ))}
              </div>
              {lu.substitutes.length > 0 && (
                <>
                  <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1.5">Reservas</p>
                  <p className="text-[11px] text-muted-foreground">{lu.substitutes.map(p => p.name).join(', ')}</p>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Estatísticas por jogador */}
      {(data.players || []).length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {data.players!.map((blk, idx) => (
            <div key={idx} className="bg-card border border-border/50 rounded-xl p-5 overflow-hidden">
              <div className="flex items-center gap-2 mb-3">
                <Logo id={blk.team_id} size={20} />
                <h3 className="text-sm font-semibold">{teamPt(blk.team || '')}</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead className="text-muted-foreground">
                    <tr className="text-left">
                      <th className="py-1 font-medium">Jogador</th>
                      <th className="py-1 font-medium text-center">Nota</th>
                      <th className="py-1 font-medium text-center">Min</th>
                      <th className="py-1 font-medium text-center">G/A</th>
                      <th className="py-1 font-medium text-center">Fin.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blk.players.map((p, i) => (
                      <tr key={i} className="border-t border-border/20">
                        <td className="py-1 truncate max-w-[120px]">{p.name}</td>
                        <td className="py-1 text-center font-mono">{p.rating ?? '-'}</td>
                        <td className="py-1 text-center font-mono">{p.minutes ?? '-'}</td>
                        <td className="py-1 text-center font-mono">{p.goals ?? 0}/{p.assists ?? 0}</td>
                        <td className="py-1 text-center font-mono">{p.shots_total ?? '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
