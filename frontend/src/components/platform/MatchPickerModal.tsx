"use client";
import React, { useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { AlertTriangle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { teamLogoUrl } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';

// Partidas anteriores a esta data são marcadas como possivelmente incompletas
// (a cobertura de estatísticas/escalações da api-football é esparsa em jogos antigos).
const OLD_MATCH_CUTOFF = '2019-01-01';
const isOldMatch = (iso?: string) => !!iso && iso.slice(0, 10) < OLD_MATCH_CUTOFF;

const OldMatchBadge = () => (
  <TooltipProvider delayDuration={150}>
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center text-amber-500 shrink-0"><AlertTriangle className="w-3.5 h-3.5" /></span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed">
        <p>Por ser uma partida antiga, algumas informações podem estar faltando.</p>
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

export type PickerFixture = {
  fixture_id: string;
  home: string;
  away: string;
  date: string;
  tournament?: string;
  neutral?: boolean;
  league_name?: string;
};

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

const Flag = ({ name, ids }: { name: string; ids: Record<string, number> }) => {
  const url = teamLogoUrl(ids[name]);
  return url ? <img src={url} alt="" className="w-5 h-5 object-contain shrink-0" loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} /> : null;
};

export function MatchPickerModal({
  open, onOpenChange, fixtures, teamIds, onSelect, title = 'Selecionar Partida',
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  fixtures: PickerFixture[];
  teamIds: Record<string, number>;
  onSelect: (fx: PickerFixture) => void;
  title?: string;
}) {
  const [comp, setComp] = useState<string>('');     // competição selecionada (label PT)
  const [compQuery, setCompQuery] = useState('');
  const [teamQuery, setTeamQuery] = useState('');
  const [dateFilter, setDateFilter] = useState('');

  const competitions = useMemo(() => {
    const set = new Map<string, string>();  // label PT -> label PT
    fixtures.forEach(f => {
      const lbl = competitionPt(f.league_name || f.tournament);
      if (lbl) set.set(lbl, lbl);
    });
    return Array.from(set.keys()).sort();
  }, [fixtures]);

  const filtered = useMemo(() => {
    return fixtures.filter(f => {
      const lbl = competitionPt(f.league_name || f.tournament);
      if (comp && lbl !== comp) return false;
      if (teamQuery) {
        const q = teamQuery.toLowerCase();
        if (!teamPt(f.home).toLowerCase().includes(q) && !teamPt(f.away).toLowerCase().includes(q)) return false;
      }
      if (dateFilter && (f.date || '').slice(0, 10) !== dateFilter) return false;
      return true;
    });
  }, [fixtures, comp, teamQuery, dateFilter]);

  const compShown = competitions.filter(c => c.toLowerCase().includes(compQuery.toLowerCase()));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-24px)] md:w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {/* Menu superior de competições + busca */}
        <div className="border-b border-border/40 pb-3">
          <Input value={compQuery} onChange={e => setCompQuery(e.target.value)} placeholder="Filtrar competição..." className="h-9 mb-2 max-w-xs" />
          <div className="flex gap-1.5 flex-wrap max-h-20 overflow-y-auto py-1">
            <button onClick={() => setComp('')}
              className={`px-3.5 py-2 sm:px-2.5 sm:py-1 rounded-md text-xs sm:text-[11px] border transition-colors flex items-center justify-center min-h-[36px] sm:min-h-0 ${comp === '' ? 'bg-primary/10 border-primary/40 text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground'}`}>
              Todas
            </button>
            {compShown.map(c => (
              <button key={c} onClick={() => setComp(c)}
                className={`px-3.5 py-2 sm:px-2.5 sm:py-1 rounded-md text-xs sm:text-[11px] border transition-colors flex items-center justify-center min-h-[36px] sm:min-h-0 ${comp === c ? 'bg-primary/10 border-primary/40 text-foreground' : 'border-border/50 text-muted-foreground hover:text-foreground'}`}>
                {c}
              </button>
            ))}
          </div>
        </div>

        {/* Filtros de equipe e data */}
        <div className="flex gap-2 flex-wrap items-center">
          <Input value={teamQuery} onChange={e => setTeamQuery(e.target.value)} placeholder="Filtrar por equipe..." className="h-9 w-full sm:max-w-xs" />
          <Input type="date" value={dateFilter} onChange={e => setDateFilter(e.target.value)} className="h-9 w-full sm:max-w-[160px]" />
        </div>

        {/* Cards de partidas */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 overflow-y-auto pr-1">
          {filtered.length === 0 && <p className="text-xs text-muted-foreground italic col-span-full py-6 text-center">Nenhuma partida encontrada com os filtros.</p>}
          {filtered.length > 80 && <p className="text-[10px] text-muted-foreground col-span-full">Mostrando 80 de {filtered.length} — refine os filtros para ver outras.</p>}
          {filtered.slice(0, 80).map(f => (
            <button key={f.fixture_id}
              onClick={() => { onSelect(f); onOpenChange(false); }}
              className="text-left p-3 rounded-lg border border-border/50 bg-muted/30 hover:border-cyan-500/40 hover:bg-muted/60 transition-colors">
              <div className="flex items-center justify-between gap-2 mb-1.5">
                <div className="flex items-center gap-1.5 min-w-0">
                  <Flag name={f.home} ids={teamIds} />
                  <span className="text-xs font-medium truncate">{teamPt(f.home)}</span>
                </div>
                <span className="text-[10px] text-muted-foreground shrink-0">x</span>
                <div className="flex items-center gap-1.5 min-w-0 justify-end">
                  <span className="text-xs font-medium truncate">{teamPt(f.away)}</span>
                  <Flag name={f.away} ids={teamIds} />
                </div>
              </div>
              <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                <span className="truncate">{competitionPt(f.league_name || f.tournament)}</span>
                <span className="flex items-center gap-1 shrink-0">
                  {isOldMatch(f.date) && <OldMatchBadge />}
                  <span className="font-mono">{fmtDateTime(f.date)}</span>
                </span>
              </div>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
