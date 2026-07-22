"use client";
import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { AlertTriangle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { teamLogoUrl, leagueLogoUrl, onImgError } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';

// Partidas anteriores a esta data são marcadas como possivelmente incompletas
// (a cobertura de estatísticas/escalações da api-football é esparsa em jogos antigos).
const OLD_MATCH_CUTOFF = '2019-01-01';
const isOldMatch = (iso?: string) => !!iso && iso.slice(0, 10) < OLD_MATCH_CUTOFF;

const COUNTRY_FLAGS: Record<string, string> = {
  "Brasil": "🇧🇷", "Mundo (Internacional)": "🌍", "Europa": "🇪🇺", "Américas": "🌎",
  "África": "🌍", "Ásia": "🌏", "Oceania": "🌏", "Inglaterra": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
  "Espanha": "🇪🇸", "Itália": "🇮🇹", "Alemanha": "🇩🇪", "França": "🇫🇷",
  "Holanda": "🇳🇱", "Portugal": "🇵🇹", "México": "🇲🇽", "Estados Unidos": "🇺🇸",
  "Argentina": "🇦🇷", "Turquia": "🇹🇷", "Bélgica": "🇧🇪", "Suécia": "🇸🇪",
  "Polônia": "🇵🇱", "Noruega": "🇳🇴", "Croácia": "🇭🇷", "Japão": "🇯🇵",
  "Coreia do Sul": "🇰🇷", "Equador": "🇪🇨", "Colômbia": "🇨🇴", "Arábia Saudita": "🇸🇦",
  "Escócia": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Grécia": "🇬🇷", "Chéquia": "🇨🇿",
};

function getCountry(compName: string, scope: 'selecao' | 'clube'): string {
  const name = compName.toLowerCase();
  if (scope === 'selecao') {
    if (name.includes("eurocopa") || name.includes("euro championship") || name.includes("nations league") || name.includes("uefa") || name.includes("qualifiers - europe") || name.includes("eliminatórias da uefa")) return "Europa";
    if (name.includes("copa américa") || name.includes("copa america") || name.includes("concacaf") || name.includes("conmebol") || name.includes("gold cup") || name.includes("eliminatórias da américa") || name.includes("eliminatórias da conmebol") || name.includes("eliminatórias da concacaf")) return "Américas";
    if (name.includes("african cup") || name.includes("copa africana") || name.includes("caf") || name.includes("eliminatórias da caf")) return "África";
    if (name.includes("asian cup") || name.includes("copa da ásia") || name.includes("afc") || name.includes("asean") || name.includes("eliminatórias da ásia")) return "Ásia";
    if (name.includes("ofc") || name.includes("eliminatórias da oceania")) return "Oceania";
    return "Mundo (Internacional)";
  }
  if (name.includes("brasileirao") || name.includes("copa do brasil") || name.includes("brasileirão")) return "Brasil";
  
  if (
    name.includes("champions league") || name.includes("libertadores") || name.includes("sul-americana") || 
    name.includes("sudamericana") || name.includes("europa league") || name.includes("conference league") || 
    name.includes("recopa") || name.includes("mundial")
  ) {
    return "Mundo (Internacional)";
  }

  if (name.includes("premier league") || name.includes("championship") || name.includes("fa cup") || name.includes("league cup")) return "Inglaterra";
  if (name.includes("la liga") || name.includes("segunda div") || name.includes("copa del rey")) return "Espanha";
  if (name.includes("serie a italia") || name.includes("serie b") || name.includes("coppa italia") || name.includes("itália")) return "Itália";
  if (name.includes("bundesliga") || name.includes("dfb pokal")) return "Alemanha";
  if (name.includes("ligue 1") || name.includes("ligue 2") || name.includes("coupe de france")) return "França";
  if (name.includes("eredivisie") || name.includes("knvb")) return "Holanda";
  if (name.includes("primeira liga") || name.includes("taça de portugal")) return "Portugal";
  if (name.includes("liga mx")) return "México";
  if (name.includes("major league soccer") || name.includes("mls")) return "Estados Unidos";
  if (name.includes("argentina") || name.includes("primera división") || name.includes("primera a") || name.includes("liga profesional")) return "Argentina";
  if (name.includes("süper lig") || name.includes("super lig")) return "Turquia";
  if (name.includes("jupiler pro league")) return "Bélgica";
  if (name.includes("allsvenskan")) return "Suécia";
  if (name.includes("ekstraklasa")) return "Polônia";
  if (name.includes("eliteserien")) return "Noruega";
  if (name.includes("hnl")) return "Croácia";
  if (name.includes("j1 league")) return "Japão";
  if (name.includes("k league 1")) return "Coreia do Sul";
  if (name.includes("liga pro")) return "Equador";
  if (name.includes("pro league") || name.includes("saudi")) return "Arábia Saudita";
  if (name.includes("premiership")) return "Escócia";
  if (name.includes("super league 1") || name.includes("grecia")) return "Grécia";
  if (name.includes("superliga")) return "Sérvia/Dinamarca";
  if (name.includes("czech liga")) return "Chéquia";

  return "Outras Competições";
}

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
  return toLocalDateStr(new Date());
}

// `f.date` vem em ISO UTC (ex. "2026-07-23T00:30:00+00:00") -- um jogo às 21:30 no
// Brasil (UTC-3) já virou "amanhã" em UTC. Comparar via `.slice(0,10)` (data crua UTC)
// contra o filtro de data LOCAL do usuário some com jogos de hoje à noite (ex. Brasileirão
// 21:30) da aba "Hoje", jogando-os pra "Amanhã" -- por isso a conversão pro fuso local
// abaixo, nunca slice direto na string ISO.
function toLocalDateStr(d: Date): string {
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const Flag = ({ name, ids }: { name: string; ids: Record<string, number> }) => {
  const url = teamLogoUrl(ids[name]);
  return url ? <img src={url} alt="" className="w-5 h-5 object-contain shrink-0" loading="lazy" onError={onImgError} /> : null;
};

// Ordem de prioridade editorial das competições de clube -- essas aparecem primeiro
// no grid, nessa ordem fixa; o restante entra depois, ordenado pela quantidade de
// jogos em aberto (mais jogos primeiro).
const PRIORITY_COMPS = [
  'Copa do Mundo FIFA', 'Liga das Nações da UEFA', 'Copa América', 'Eurocopa',
  'Brasileirao Serie A', 'Brasileirao Serie B', 'Copa do Brasil',
  'Champions League', 'Premier League', 'La Liga',
];
const compRank = (label: string) => {
  const i = PRIORITY_COMPS.indexOf(label);
  return i === -1 ? PRIORITY_COMPS.length : i;
};

export function MatchPickerModal({
  open, onOpenChange, fixtures, teamIds, onSelect, title = 'Selecionar Partida', defaultScope = 'selecao',
  dateDefault = 'none', allCompetitions,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  fixtures: PickerFixture[];
  teamIds: Record<string, number>;
  onSelect: (fx: PickerFixture) => void;
  title?: string;
  defaultScope?: 'selecao' | 'clube';
  /** 'today' pré-seleciona a data atual; 'none' (padrão) deixa sem filtro de data,
   * mostrando todas as competições/partidas em aberto. */
  dateDefault?: 'today' | 'none';
  /** Catálogo completo de competições treinadas (ambos escopos) -- quando informado,
   * TODA competição aparece no grid, mesmo sem jogo agendado (com badge e desabilitada). */
  allCompetitions?: { selecao: string[]; clube: string[] };
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
    () => scopedFixtures.filter(f => !dateFilter || (f.date && toLocalDateStr(new Date(f.date)) === dateFilter)),
    [scopedFixtures, dateFilter]
  );

  // Uma linha por competição: label PT + um league_id representativo (p/ logo).
  // Também inclui competições SEM jogo agendado no filtro atual (via `allCompetitions`,
  // o catálogo completo de treino) -- essas entram com `fixtures: []` e o grid as
  // renderiza desabilitadas, com o badge "Sem jogos agendados".
  const competitions = useMemo(() => {
    const map = new Map<string, { label: string; leagueId: number | null; fixtures: PickerFixture[] }>();
    (allCompetitions?.[scope] || []).forEach(raw => {
      const label = competitionPt(raw);
      if (!label) return;
      if (!map.has(label)) map.set(label, { label, leagueId: null, fixtures: [] });
    });
    dateFiltered.forEach(f => {
      const label = competitionPt(f.league_name || f.tournament);
      if (!label) return;
      if (!map.has(label)) map.set(label, { label, leagueId: f.league_id ?? null, fixtures: [] });
      const entry = map.get(label)!;
      if (entry.leagueId == null && f.league_id != null) entry.leagueId = f.league_id;
      entry.fixtures.push(f);
    });
    return Array.from(map.values()).sort((a, b) => {
      const ra = compRank(a.label), rb = compRank(b.label);
      if (ra !== rb) return ra - rb;
      if (a.fixtures.length === 0 && b.fixtures.length > 0) return 1;
      if (b.fixtures.length === 0 && a.fixtures.length > 0) return -1;
      return b.fixtures.length - a.fixtures.length || a.label.localeCompare(b.label);
    });
  }, [dateFiltered, allCompetitions, scope]);

  const q = query.trim().toLowerCase();
  const matchesTeamQuery = (f: PickerFixture) =>
    teamPt(f.home).toLowerCase().includes(q) || teamPt(f.away).toLowerCase().includes(q);

  // Busca única: por nome de competição OU por clube/seleção com jogo agendado nela, OU país.
  const compsShown = useMemo(() => {
    if (!q) return competitions;
    return competitions.filter(c => {
      const country = getCountry(c.label, scope).toLowerCase();
      return c.label.toLowerCase().includes(q) || country.includes(q) || c.fixtures.some(matchesTeamQuery);
    });
  }, [competitions, q, scope]);

  const groupedComps = useMemo(() => {
    const groups: Record<string, typeof compsShown> = {};
    compsShown.forEach(c => {
      const country = getCountry(c.label, scope);
      if (!groups[country]) groups[country] = [];
      groups[country].push(c);
    });

    return Object.entries(groups).map(([country, comps]) => ({
      country,
      comps,
      rank: country === "Brasil" ? 0 : country === "Mundo (Internacional)" ? 1 : country === "Europa" ? 2 : country === "Américas" ? 3 : country === "África" ? 4 : country === "Ásia" ? 5 : country === "Outras Competições" ? 999 : 6
    })).sort((a, b) => {
      if (a.rank !== b.rank) return a.rank - b.rank;
      return a.country.localeCompare(b.country);
    });
  }, [compsShown, scope]);

  // Se o filtro atual não deixa mais a competição escolhida visível, volta pra grade.
  useEffect(() => {
    if (comp && !compsShown.some(c => c.label === comp)) setComp('');
  }, [compsShown, comp]);

  const selectedMatches = useMemo(() => {
    if (!comp) return [];
    const group = competitions.find(c => c.label === comp);
    if (!group) return [];
    // Se a busca bateu no nome da competição, mantém todas; senão, restringe pelo time buscado.
    const matches = !q || group.label.toLowerCase().includes(q)
      ? group.fixtures : group.fixtures.filter(matchesTeamQuery);
    // Da data mais próxima até a mais distante no futuro.
    return [...matches].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
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
          <div className="overflow-y-auto pr-1">
            {groupedComps.length === 0 && (
              <p className="text-xs text-muted-foreground italic col-span-full py-6 text-center">
                Nenhuma competição com partida agendada para esse filtro.
              </p>
            )}
            <div className="space-y-6 pb-2">
              {groupedComps.map(g => (
                <div key={g.country}>
                  <div className="flex items-center gap-2 mb-3">
                    <h3 className="text-sm font-semibold text-foreground tracking-tight flex items-center gap-1.5">
                      {COUNTRY_FLAGS[g.country] && <span>{COUNTRY_FLAGS[g.country]}</span>}
                      {g.country}
                    </h3>
                    <div className="flex-1 h-px bg-border/40"></div>
                  </div>
                  <div className="grid grid-cols-3 sm:grid-cols-4 gap-2.5">
                    {g.comps.map(c => {
                      let logo = leagueLogoUrl(c.leagueId);
                      if (!logo && scope === 'selecao') {
                        const lname = c.label.toLowerCase();
                        if (lname.includes("copa do mundo fifa") || lname.includes("world cup")) logo = leagueLogoUrl(1);
                        else if (lname.includes("eurocopa") || lname.includes("euro championship")) logo = leagueLogoUrl(4);
                        else if (lname.includes("copa américa") || lname.includes("copa america")) logo = leagueLogoUrl(9);
                        else if (lname.includes("nations league")) logo = leagueLogoUrl(66);
                        else if (lname.includes("african cup") || lname.includes("copa africana")) logo = leagueLogoUrl(6);
                        else if (lname.includes("asian cup") || lname.includes("copa da ásia")) logo = leagueLogoUrl(7);
                      }
                      const empty = c.fixtures.length === 0;
                      return (
                        <button key={c.label} onClick={() => { if (!empty) setComp(c.label); }}
                          disabled={empty}
                          aria-disabled={empty}
                          className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-colors ${
                            empty
                              ? 'border-border/30 bg-muted/10 opacity-50 cursor-not-allowed'
                              : 'border-border/50 bg-muted/30 hover:border-cyan-500/40 hover:bg-muted/60'
                          }`}>
                          {logo && (
                            <img src={logo} alt="" className="w-8 h-8 object-contain" loading="lazy"
                              onError={onImgError} />
                          )}
                          <span className="text-[11px] font-medium text-center leading-snug">{c.label}</span>
                          {empty && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground leading-tight">
                              Sem jogos agendados
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
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
