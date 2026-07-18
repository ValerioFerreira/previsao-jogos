"use client";
import React, { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { AlertTriangle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { teamLogoUrl, leagueLogoUrl } from '@/lib/api';
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
  league_id?: number | null;
  scope?: 'selecao' | 'clube';
};

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function todayISO(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

// Em dev, o primeiro carregamento de imagem cross-origin às vezes é abortado pelo
// double-render do React StrictMode -- um retry único evita esconder um brasão válido.
function onImgError(e: React.SyntheticEvent<HTMLImageElement>) {
  const img = e.currentTarget;
  if (!img.dataset.retried) {
    img.dataset.retried = '1';
    const src = img.src;
    img.src = '';
    img.src = src;
  } else {
    img.style.display = 'none';
  }
}

const Flag = ({ name, ids }: { name: string; ids: Record<string, number> }) => {
  const url = teamLogoUrl(ids[name]);
  return url ? <img src={url} alt="" className="w-5 h-5 object-contain shrink-0" loading="lazy" onError={onImgError} /> : null;
};

export function MatchPickerModal({
  open, onOpenChange, fixtures, teamIds, onSelect, title = 'Selecionar Partida', defaultScope = 'selecao',
  dateDefault = 'today',
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  fixtures: PickerFixture[];
  teamIds: Record<string, number>;
  onSelect: (fx: PickerFixture) => void;
  title?: string;
  defaultScope?: 'selecao' | 'clube';
  /** 'today' pré-seleciona a data atual (partidas futuras); 'none' deixa sem filtro
   * de data (partidas passadas, onde "hoje" nunca bateria com nada). */
  dateDefault?: 'today' | 'none';
}) {
  const [scope, setScope] = useState<'selecao' | 'clube'>(defaultScope);
  const [dateFilter, setDateFilter] = useState(dateDefault === 'today' ? todayISO() : '');
  const [query, setQuery] = useState('');
  const [comp, setComp] = useState<string>('');

  // Reabrir o modal reaplica o escopo atual da tela e reseta a competição escolhida.
  useEffect(() => {
    if (open) { setScope(defaultScope); setComp(''); setDateFilter(dateDefault === 'today' ? todayISO() : ''); }
  }, [open, defaultScope, dateDefault]);

  const scopedFixtures = useMemo(
    () => fixtures.filter(f => (f.scope || 'selecao') === scope),
    [fixtures, scope]
  );

  const dateFiltered = useMemo(
    () => scopedFixtures.filter(f => !dateFilter || (f.date || '').slice(0, 10) === dateFilter),
    [scopedFixtures, dateFilter]
  );

  // Uma linha por competição: label PT + um league_id representativo (p/ logo).
  const competitions = useMemo(() => {
    const map = new Map<string, { label: string; leagueId: number | null; fixtures: PickerFixture[] }>();
    dateFiltered.forEach(f => {
      const label = competitionPt(f.league_name || f.tournament);
      if (!label) return;
      if (!map.has(label)) map.set(label, { label, leagueId: f.league_id ?? null, fixtures: [] });
      map.get(label)!.fixtures.push(f);
    });
    return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label));
  }, [dateFiltered]);

  const q = query.trim().toLowerCase();
  const matchesTeamQuery = (f: PickerFixture) =>
    teamPt(f.home).toLowerCase().includes(q) || teamPt(f.away).toLowerCase().includes(q);

  // Busca única: por nome de competição OU por clube/seleção com jogo agendado nela.
  const compsShown = useMemo(() => {
    if (!q) return competitions;
    return competitions.filter(c => c.label.toLowerCase().includes(q) || c.fixtures.some(matchesTeamQuery));
  }, [competitions, q]);

  // Se o filtro atual não deixa mais a competição escolhida visível, volta pra grade.
  useEffect(() => {
    if (comp && !compsShown.some(c => c.label === comp)) setComp('');
  }, [compsShown, comp]);

  const selectedMatches = useMemo(() => {
    if (!comp) return [];
    const group = competitions.find(c => c.label === comp);
    if (!group) return [];
    if (!q) return group.fixtures;
    // Se a busca bateu no nome da competição, mantém todas; senão, restringe pelo time buscado.
    return group.label.toLowerCase().includes(q) ? group.fixtures : group.fixtures.filter(matchesTeamQuery);
  }, [comp, competitions, q]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-24px)] md:w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {/* Escopo (Seleções Nacionais / Clubes) + data, na mesma linha */}
        <div className="flex items-center justify-between gap-2 flex-wrap border-b border-border/40 pb-3">
          <div className="inline-flex p-1 rounded-lg bg-muted text-xs font-medium">
            <button onClick={() => setScope('selecao')}
              className={`px-3 py-1.5 rounded-md transition-colors ${scope === 'selecao' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              Seleções Nacionais
            </button>
            <button onClick={() => setScope('clube')}
              className={`px-3 py-1.5 rounded-md transition-colors ${scope === 'clube' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              Clubes
            </button>
          </div>
          <Input type="date" value={dateFilter} onChange={e => setDateFilter(e.target.value)} className="h-9 w-auto" />
        </div>

        {/* Busca única de competição ou equipe */}
        <div>
          <Input value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar competição ou equipe" className="h-9" />
        </div>

        {!comp ? (
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5 overflow-y-auto pr-1 content-start">
            {compsShown.length === 0 && (
              <p className="text-xs text-muted-foreground italic col-span-full py-6 text-center">
                Nenhuma competição com partida agendada para esse filtro.
              </p>
            )}
            {compsShown.map(c => {
              const logo = leagueLogoUrl(c.leagueId);
              return (
                <button key={c.label} onClick={() => setComp(c.label)}
                  className="flex flex-col items-center gap-1.5 p-3 rounded-xl border border-border/50 bg-muted/30 hover:border-cyan-500/40 hover:bg-muted/60 transition-colors">
                  {logo && (
                    <img src={logo} alt="" className="w-8 h-8 object-contain" loading="lazy"
                      onError={onImgError} />
                  )}
                  <span className="text-[11px] font-medium text-center leading-snug">{c.label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <button onClick={() => setComp('')} className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                ← Voltar às competições
              </button>
              <span className="text-xs font-medium">{comp}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 overflow-y-auto pr-1">
              {selectedMatches.length === 0 && <p className="text-xs text-muted-foreground italic col-span-full py-6 text-center">Nenhuma partida encontrada com os filtros.</p>}
              {selectedMatches.length > 80 && <p className="text-[10px] text-muted-foreground col-span-full">Mostrando 80 de {selectedMatches.length} — refine os filtros para ver outras.</p>}
              {selectedMatches.slice(0, 80).map(f => (
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
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
