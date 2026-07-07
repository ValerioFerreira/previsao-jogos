"use client";
import React from 'react';
import { MatchDetail as MD, MatchPlayer, LineupPlayer, teamLogoUrl, playerPhotoUrl } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';
import InfoTooltip from '@/components/platform/InfoTooltip';
import MatchPlayerStats from '@/components/platform/MatchPlayerStats';

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

function ratingColor(r?: string | null): string {
  const v = r ? parseFloat(r) : NaN;
  if (isNaN(v)) return 'bg-muted text-muted-foreground';
  if (v >= 7.5) return 'bg-emerald-500 text-white';
  if (v >= 6.5) return 'bg-lime-500 text-white';
  if (v >= 6.0) return 'bg-amber-500 text-white';
  return 'bg-red-500 text-white';
}

// Balão de estatísticas do jogador (foto, número, nome, stats do jogo).
function StatBalloon({ p, st }: { p: LineupPlayer; st?: MatchPlayer }) {
  const rows: [string, React.ReactNode][] = [
    ['Nota', st?.rating ?? '-'],
    ['Minutos', st?.minutes ?? '-'],
    ['Gols / Assist.', `${st?.goals ?? 0} / ${st?.assists ?? 0}`],
    ['Finalizações', `${st?.shots_total ?? 0} (${st?.shots_on ?? 0} no gol)`],
    ['Passes', `${st?.passes ?? '-'}${st?.key_passes != null ? ` (${st.key_passes} chave)` : ''}`],
    ['Desarmes', st?.tackles ?? '-'],
    ['Cartões', `${st?.yellow ?? 0}🟨 ${st?.red ?? 0}🟥`],
  ];
  return (
    <div className="w-44 rounded-lg border border-border/60 bg-popover shadow-xl p-2.5 text-left">
      <div className="flex items-center gap-2 mb-2 pb-2 border-b border-border/40">
        {playerPhotoUrl(p.id) && <img src={playerPhotoUrl(p.id)!} alt="" className="w-9 h-9 rounded-full object-cover bg-muted" loading="lazy" onError={hideOnError} />}
        <div className="min-w-0">
          <p className="text-[11px] font-semibold leading-tight truncate">{p.number ? `${p.number}. ` : ''}{p.name}</p>
          {p.pos && <p className="text-[9px] text-muted-foreground">{p.pos}</p>}
        </div>
      </div>
      <div className="space-y-0.5">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-[10px]">
            <span className="text-muted-foreground">{k}</span>
            <span className="font-mono font-medium">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Jogador posicionado no campo (foto, número, nome, nota) + balão no hover.
function FieldPlayer({ p, st, top, left }: { p: LineupPlayer; st?: MatchPlayer; top: number; left: number }) {
  return (
    <div className="group absolute -translate-x-1/2 -translate-y-1/2 flex flex-col items-center" style={{ top: `${top}%`, left: `${left}%` }}>
      <div className="relative">
        <div className="w-9 h-9 rounded-full bg-muted ring-2 ring-white/70 overflow-hidden shadow">
          {playerPhotoUrl(p.id)
            ? <img src={playerPhotoUrl(p.id)!} alt="" className="w-full h-full object-cover" loading="lazy" onError={hideOnError} />
            : <span className="flex items-center justify-center w-full h-full text-[11px] font-bold text-muted-foreground">{p.number ?? '?'}</span>}
        </div>
        {p.number != null && (
          <span className="absolute -top-1 -left-1 bg-background/90 text-foreground text-[8px] font-bold font-mono rounded-full w-4 h-4 flex items-center justify-center border border-border/60">{p.number}</span>
        )}
        {st?.rating && (
          <span className={`absolute -bottom-1 left-1/2 -translate-x-1/2 text-[8px] font-bold font-mono rounded px-1 leading-tight ${ratingColor(st.rating)}`}>{parseFloat(st.rating).toFixed(1)}</span>
        )}
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block z-30 pointer-events-none">
          <StatBalloon p={p} st={st} />
        </div>
      </div>
      <span className="mt-1.5 text-[9px] font-medium text-white text-center leading-tight max-w-[68px] truncate drop-shadow">{p.name?.split(' ').slice(-1)[0]}</span>
    </div>
  );
}

// Campo com o XI titular posicionado pelo `grid` (linha:coluna) da API.
function FieldLineup({ lu, statsById }: { lu: NonNullable<MD['lineups']>[number]; statsById: Map<number, MatchPlayer> }) {
  const byRow = new Map<number, (LineupPlayer & { col: number })[]>();
  lu.startXI.forEach((p) => {
    const [r, c] = (p.grid || '1:1').split(':').map(Number);
    if (!byRow.has(r)) byRow.set(r, []);
    byRow.get(r)!.push({ ...p, col: c || 1 });
  });
  const rowNums = [...byRow.keys()].sort((a, b) => a - b);
  const maxRow = rowNums.length ? rowNums[rowNums.length - 1] : 1;

  const subs = lu.substitutes.map((p) => ({ p, st: p.id ? statsById.get(p.id) : undefined }));
  const playedSubs = subs.filter((s) => (s.st?.minutes ?? 0) > 0);
  const benchSubs = subs.filter((s) => (s.st?.minutes ?? 0) === 0 || s.st == null);

  return (
    <div>
      {/* Campo */}
      <div className="relative w-full rounded-lg bg-gradient-to-b from-emerald-700/90 to-emerald-900/90 border border-emerald-950/40" style={{ aspectRatio: '3 / 4' }}>
        <div className="absolute left-2 right-2 top-1/2 h-px bg-white/25" />
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-14 h-14 rounded-full border border-white/25" />
        <div className="absolute left-1/2 -translate-x-1/2 bottom-1 w-1/2 h-[13%] border border-white/25 border-b-0 rounded-t-sm" />
        <div className="absolute left-1/2 -translate-x-1/2 top-1 w-1/2 h-[13%] border border-white/25 border-t-0 rounded-b-sm" />
        {rowNums.map((r) => {
          const players = byRow.get(r)!.slice().sort((a, b) => a.col - b.col);
          // linha 1 (goleiro) embaixo; linhas maiores (ataque) em cima
          const top = maxRow > 1 ? 90 - ((r - 1) / (maxRow - 1)) * 80 : 50;
          return players.map((p, j) => {
            const left = ((j + 1) / (players.length + 1)) * 100;
            return <FieldPlayer key={`${r}-${j}`} p={p} st={p.id ? statsById.get(p.id) : undefined} top={top} left={left} />;
          });
        })}
      </div>

      {/* Reservas: quem entrou (com ícone de substituição + balão no hover) e demais */}
      {subs.length > 0 && (
        <div className="mt-3">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5">Reservas</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1.5">
            {playedSubs.map(({ p, st }, i) => (
              <div key={`in-${i}`} className="group relative">
                <span className="text-[12px] cursor-default border-b border-dashed border-emerald-500/60 flex items-center gap-0.5">
                  <span className="text-emerald-500 text-[10px]" title="Entrou em campo">▲</span>
                  {p.number ? `${p.number}. ` : ''}{p.name}
                  {st?.rating && <span className={`ml-1 text-[8px] font-mono rounded px-1 ${ratingColor(st.rating)}`}>{parseFloat(st.rating).toFixed(1)}</span>}
                </span>
                <div className="absolute bottom-full left-0 mb-1 hidden group-hover:block z-30">
                  <StatBalloon p={p} st={st} />
                </div>
              </div>
            ))}
            {benchSubs.map(({ p }, i) => (
              <span key={`b-${i}`} className="text-[12px] text-muted-foreground">{p.name}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

type MinFallback = { home: string; away: string; date: string; teamIds: Record<string, number> };

export function MatchDetail({ data, fallback }: { data: MD; fallback?: MinFallback }) {
  const statsRef = React.useRef<HTMLDivElement>(null);
  const [timelineMaxH, setTimelineMaxH] = React.useState<number | null>(null);

  React.useLayoutEffect(() => {
    const el = statsRef.current;
    if (!el) { setTimelineMaxH(null); return; }
    const update = () => setTimelineMaxH(el.getBoundingClientRect().height);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [data]);

  if (!data?.found || !data.info) {
    if (fallback) {
      return (
        <div className="space-y-6">
          <div className="bg-card border border-border/50 rounded-xl p-6">
            <div className="flex items-center justify-center gap-2 text-[0.94rem] text-muted-foreground mb-4">
              <span>{dBR(fallback.date)}</span>
            </div>
            <div className="flex items-center justify-center gap-4 sm:gap-8">
              <div className="text-center flex-1">
                <Logo id={fallback.teamIds[fallback.home]} size={60} />
                <p className="font-semibold mt-1 text-[1.09rem]">{teamPt(fallback.home)}</p>
              </div>
              <span className="text-[2.34rem] font-bold font-mono text-muted-foreground shrink-0">x</span>
              <div className="text-center flex-1">
                <Logo id={fallback.teamIds[fallback.away]} size={60} />
                <p className="font-semibold mt-1 text-[1.09rem]">{teamPt(fallback.away)}</p>
              </div>
            </div>
          </div>
          <p className="text-center py-6 text-muted-foreground text-sm">
            Estatísticas completas indisponíveis para esta partida.
          </p>
        </div>
      );
    }
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
  const hasStats = statByTeam.length > 0;
  const hasEvents = (data.events || []).length > 0;

  return (
    <div className="space-y-6">
      {/* Cabeçalho ("Detalhe da Partida") */}
      <div className="bg-card border border-border/50 rounded-xl p-6">
        <div className="flex items-center justify-center gap-2 text-[0.94rem] text-muted-foreground mb-4">
          {info.league_logo && <img src={info.league_logo} alt="" className="w-5 h-5 object-contain" onError={hideOnError} />}
          <span>{competitionPt(info.league)}{info.round ? ` · ${info.round}` : ''} · {dBR(info.date)}</span>
        </div>
        <div className="flex items-center justify-center gap-4 sm:gap-8">
          <div className="text-center flex-1">
            <Logo id={info.home_id} size={60} />
            <p className="font-semibold mt-1 text-[1.09rem]">{teamPt(info.home || '')}</p>
          </div>
          <div className="text-center shrink-0">
            <p className="text-[2.34rem] font-bold font-mono">{g.home ?? '-'} <span className="text-muted-foreground">x</span> {g.away ?? '-'}</p>
            {ht && ht.home != null && <p className="text-[13px] text-muted-foreground mt-1">1º tempo: {ht.home}-{ht.away}</p>}
          </div>
          <div className="text-center flex-1">
            <Logo id={info.away_id} size={60} />
            <p className="font-semibold mt-1 text-[1.09rem]">{teamPt(info.away || '')}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[14px] text-muted-foreground mt-4 border-t border-border/30 pt-3">
          {info.venue && <span>🏟️ {info.venue}{info.city ? `, ${info.city}` : ''}</span>}
          {info.referee && <span>👨‍⚖️ {info.referee}</span>}
        </div>
      </div>

      {/* Estatísticas da Partida (esquerda) + Linha do Tempo (direita, mesma altura + scroll) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
        {hasStats && (
          <div ref={statsRef} className="bg-card border border-border/50 rounded-xl p-5">
            <h3 className="text-base font-semibold mb-4 text-center">Estatísticas da Partida</h3>
            <div className="space-y-2">
              {STAT_ROWS.filter(([k]) => homeStats[k] != null || awayStats[k] != null).map(([k, label]) => (
                <div key={k} className="grid grid-cols-3 items-center text-[0.85rem]">
                  <span className="font-mono font-semibold text-left text-emerald-400">{homeStats[k] ?? '-'}</span>
                  <span className="text-center text-muted-foreground">{label}</span>
                  <span className="font-mono font-semibold text-right text-cyan-400">{awayStats[k] ?? '-'}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {hasEvents && (
          <div
            className="bg-card border border-border/50 rounded-xl p-5 flex flex-col min-h-0"
            style={hasStats && timelineMaxH ? { maxHeight: timelineMaxH } : undefined}
          >
            <h3 className="text-base font-semibold mb-4 text-center shrink-0">Linha do Tempo</h3>
            <div className="space-y-1.5 overflow-y-auto pr-1 flex-1 min-h-0">
              {data.events!.map((e, i) => {
                const isHome = (e.team_id != null && info.home_id != null)
                  ? e.team_id === info.home_id
                  : e.team === info.home;
                return (
                  <div key={i} className={`flex items-center gap-2 text-[0.85rem] ${isHome ? 'flex-row' : 'flex-row-reverse text-right'}`}>
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
      </div>

      {/* Destaques + tabela de estatísticas por jogador (ordenável, drill-down do hover) */}
      <MatchPlayerStats data={data} />

      {/* Escalações em campo (foto/número/nome/nota + stats no hover) por equipe.
          Os blocos `players` (com as estatísticas) são a fonte autoritária do time de
          cada jogador — a API às vezes troca o rótulo do time na ESCALAÇÃO, então
          casamos por id de jogador (stats globais + time real pela maioria do XI). */}
      {(data.lineups || []).length > 0 && (() => {
        const statsById = new Map<number, MatchPlayer>();
        const playerTeam = new Map<number, number>();
        (data.players || []).forEach((pb) => (pb.players || []).forEach((p) => {
          if (p.id != null) { statsById.set(p.id, p); if (pb.team_id != null) playerTeam.set(p.id, pb.team_id); }
        }));
        const realTeam = (lu: NonNullable<MD['lineups']>[number]): number | null => {
          const counts = new Map<number, number>();
          lu.startXI.forEach((p) => { const tid = p.id != null ? playerTeam.get(p.id) : undefined; if (tid != null) counts.set(tid, (counts.get(tid) || 0) + 1); });
          let best: number | null = null, bestN = -1;
          counts.forEach((n, tid) => { if (n > bestN) { bestN = n; best = tid; } });
          return best ?? lu.team_id;
        };
        return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-4 gap-y-4 items-start">
          {[{ id: info.home_id, name: info.home }, { id: info.away_id, name: info.away }].map((team, ti) => {
            const lu = (data.lineups || []).find(l => realTeam(l) === team.id)
              || (data.lineups || []).find(l => l.team_id === team.id)
              || (data.lineups || [])[ti];
            if (!lu) return <div key={ti} />;
            return (
              <div key={ti} className="space-y-3">
                <div className="sticky top-[3.25rem] z-20 -mb-1 pt-2 pb-3 bg-background/85 backdrop-blur-md rounded-b-xl flex flex-col items-center">
                  <Logo id={team.id} size={52} />
                  <p className="font-bold mt-1 text-[1.05rem]">{teamPt(team.name || '')}</p>
                </div>
                <div className="bg-card border border-border/50 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-base font-semibold">Escalação</h3>
                    <div className="text-right">
                      {lu.formation && <span className="text-[11px] text-muted-foreground font-mono">{lu.formation}</span>}
                      {lu.coach?.name && <p className="text-[10px] text-muted-foreground">Téc.: {lu.coach.name}</p>}
                    </div>
                  </div>
                  <FieldLineup lu={lu} statsById={statsById} />
                </div>
              </div>
            );
          })}
        </div>
        );
      })()}
    </div>
  );
}
