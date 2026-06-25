"use client";
import React from 'react';
import { teamLogoUrl } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';

function fmtDateTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

const Side = ({ name, id, role, align }: { name: string; id?: number; role: string; align: 'left' | 'right' }) => {
  const url = teamLogoUrl(id);
  return (
    <div className={`flex items-center gap-2 min-w-0 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      {url && <img src={url} alt="" className="w-7 h-7 object-contain shrink-0" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} />}
      <div className="min-w-0">
        <p className="text-sm font-semibold truncate">{teamPt(name)}</p>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{role}</p>
      </div>
    </div>
  );
};

// Cabeçalho fixo (sticky) da partida selecionada — fica sempre visível no scroll, com
// leve transparência e fade na borda inferior para não atrapalhar a leitura.
export function MatchHeader({
  home, away, teamIds, competition, date, venue, referee, neutral,
}: {
  home: string; away: string; teamIds: Record<string, number>;
  competition?: string; date?: string; venue?: string | null; referee?: string | null; neutral?: boolean;
}) {
  if (!home || !away) return null;
  const meta = [
    competition,
    fmtDateTime(date),
    venue ? `🏟️ ${venue}` : '',
    typeof neutral === 'boolean' ? (neutral ? '🏟️ Campo neutro' : '🏟️ Com mando de campo') : '',
    referee ? `👨‍⚖️ ${referee}` : '',
  ].filter(Boolean);

  return (
    <div className="sticky top-14 z-30">
      <div className="relative bg-card/80 backdrop-blur-md border border-border/50 rounded-xl px-4 py-2.5 shadow-sm">
        <div className="flex items-center justify-center gap-4 sm:gap-8">
          <div className="flex-1 flex justify-end"><Side name={home} id={teamIds[home]} role="Mandante" align="right" /></div>
          <span className="text-xs text-muted-foreground shrink-0">x</span>
          <div className="flex-1 flex justify-start"><Side name={away} id={teamIds[away]} role="Visitante" align="left" /></div>
        </div>
        {meta.length > 0 && (
          <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground mt-1">
            {meta.map((m, i) => <span key={i}>{m}</span>)}
          </div>
        )}
        {/* fade na borda inferior */}
        <div className="absolute left-2 right-2 -bottom-2.5 h-2.5 bg-gradient-to-b from-background/70 to-transparent pointer-events-none" />
      </div>
    </div>
  );
}
