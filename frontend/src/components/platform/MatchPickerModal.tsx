"use client";
import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { AlertTriangle, Check, Search, Calendar, Globe, Clock } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { teamLogoUrl, leagueLogoUrl, onImgError } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { competitionPt } from '@/lib/competitionNames';
import { useAuth } from '@/lib/AuthContext';

const OLD_MATCH_CUTOFF = '2019-01-01';
const isOldMatch = (iso?: string) => !!iso && iso.slice(0, 10) < OLD_MATCH_CUTOFF;

function startsInLessThanHour(iso?: string): boolean {
  if (!iso) return false;
  const matchTime = new Date(iso).getTime();
  if (isNaN(matchTime)) return false;
  const now = Date.now();
  const diffMs = matchTime - now;
  return diffMs > 0 && diffMs <= 3600000;
}

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
        <span className="inline-flex items-center text-amber-400 shrink-0"><AlertTriangle className="w-3.5 h-3.5" /></span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs text-xs leading-relaxed bg-popover/95 border-border/80 p-2.5">
        <p>Por ser uma partida antiga, algumas informações podem estar faltando.</p>
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

const H2HBadge = () => (
  <TooltipProvider delayDuration={150}>
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-500 text-slate-950 shadow-md border-2 border-background ring-1 ring-emerald-500/30 shrink-0">
          <Check className="w-3 h-3 stroke-[3]" />
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="text-[11px] bg-slate-900 border border-emerald-500/40 text-emerald-200 shadow-xl">
        Confronto direto disponível no banco de dados
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
);

const StartingSoonBadge = () => (
  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full bg-red-500/20 border border-red-500/50 text-red-400 text-[9px] font-mono font-extrabold uppercase tracking-wider animate-pulse shadow-md shadow-red-500/30 backdrop-blur-md">
    <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
    Inicia em menos de 1 hora
  </span>
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
  has_h2h?: boolean;
};

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())} · ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

function todayISO(): string {
  return toLocalDateStr(new Date());
}

function toLocalDateStr(d: Date): string {
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

const Flag = ({ name, ids }: { name: string; ids: Record<string, number> }) => {
  const url = teamLogoUrl(ids[name]);
  return url ? <img src={url} alt="" className="w-5 h-5 object-contain shrink-0 drop-shadow-sm" loading="lazy" onError={onImgError} /> : null;
};

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
  open, onOpenChange, fixtures, teamIds, onSelect, title = 'Selecionar Partida Agendada', defaultScope = 'selecao',
  dateDefault = 'none', allCompetitions,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  fixtures: PickerFixture[];
  teamIds: Record<string, number>;
  onSelect: (fx: PickerFixture) => void;
  title?: string;
  defaultScope?: 'selecao' | 'clube';
  dateDefault?: 'today' | 'none';
  allCompetitions?: { selecao: string[]; clube: string[] };
}) {
  const { user } = useAuth();
  const isOwnerOrManager = user && (user.role === 'owner' || user.role === 'manager' || user.email === 'valerioeducfin@gmail.com');

  const [scope, setScope] = useState<'selecao' | 'clube'>(defaultScope);
  const [dateFilter, setDateFilter] = useState(dateDefault === 'today' ? todayISO() : '');
  const [query, setQuery] = useState('');
  const [comp, setComp] = useState<string>('');

  useEffect(() => {
    if (open) { setScope(defaultScope); setComp(''); setDateFilter(dateDefault === 'today' ? todayISO() : ''); }
  }, [open, defaultScope, dateDefault]);

  const isPastMode = title.toLowerCase().includes('passada');

  const filteredFixtures = useMemo(
    () => fixtures.filter(f => {
      if (!f.date) return false;
      const matchTime = new Date(f.date).getTime();
      if (isNaN(matchTime)) return false;
      return isPastMode ? matchTime <= Date.now() : matchTime > Date.now();
    }),
    [fixtures, isPastMode]
  );

  const scopedFixtures = useMemo(
    () => filteredFixtures.filter(f => (f.scope || 'selecao') === scope),
    [filteredFixtures, scope]
  );

  const dateFiltered = useMemo(
    () => scopedFixtures.filter(f => !dateFilter || (f.date && toLocalDateStr(new Date(f.date)) === dateFilter)),
    [scopedFixtures, dateFilter]
  );

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

  useEffect(() => {
    if (comp && !compsShown.some(c => c.label === comp)) setComp('');
  }, [compsShown, comp]);

  const selectedMatches = useMemo(() => {
    if (!comp) return [];
    const group = competitions.find(c => c.label === comp);
    if (!group) return [];
    const matches = !q || group.label.toLowerCase().includes(q)
      ? group.fixtures : group.fixtures.filter(matchesTeamQuery);
    return [...matches].sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  }, [comp, competitions, q]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-24px)] md:w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col p-5 sm:p-6 bg-card border-border/80 rounded-2xl shadow-2xl">
        <DialogHeader className="pb-2 border-b border-border/40">
          <DialogTitle className="text-base font-bold text-foreground flex items-center gap-2">
            <Globe className="w-4 h-4 text-emerald-400" />
            {title}
          </DialogTitle>
        </DialogHeader>

        {/* Escopo + Filtros de Data (Com SELECIONAR SOMENTE JOGOS DE HOJE e Calendário Estilizado) */}
        <div className="flex items-center justify-between gap-3 flex-wrap pt-2">
          <div className="bg-muted/40 p-1 rounded-xl flex text-xs font-semibold border border-border/50">
            <button onClick={() => setScope('selecao')}
              className={`px-3 py-1.5 rounded-lg transition-all ${scope === 'selecao' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              Seleções Nacionais
            </button>
            <button onClick={() => setScope('clube')}
              className={`px-3 py-1.5 rounded-lg transition-all ${scope === 'clube' ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
              Clubes
            </button>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setDateFilter(dateFilter === todayISO() ? '' : todayISO())}
              className={`text-[11px] font-mono font-bold uppercase tracking-wider px-3 py-1.5 rounded-xl border transition-all cursor-pointer flex items-center gap-1.5 ${
                dateFilter === todayISO()
                  ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400 shadow-sm'
                  : 'bg-muted/30 border-border/60 text-muted-foreground hover:text-foreground hover:bg-muted/60'
              }`}
            >
              <Calendar className="w-3.5 h-3.5" />
              <span>SELECIONAR SOMENTE JOGOS DE HOJE</span>
            </button>

            <div className="flex items-center gap-2 bg-card/80 px-3 py-1.5 rounded-xl border border-border/60 hover:border-emerald-500/40 transition-colors shadow-sm">
              <Calendar className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <input
                type="date"
                value={dateFilter}
                onChange={e => setDateFilter(e.target.value)}
                className="h-6 bg-transparent border-none p-0 text-xs font-mono text-foreground focus:outline-none cursor-pointer [color-scheme:dark]"
              />
              {dateFilter && (
                <button onClick={() => setDateFilter('')} title="Limpar data" className="text-muted-foreground hover:text-foreground text-xs px-1">
                  ×
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Busca */}
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={e => setQuery(e.target.value)} placeholder="Buscar competição ou equipe..." className="h-10 pl-9 text-xs rounded-xl bg-muted/30 border-border/50 focus-visible:ring-emerald-500/40" />
        </div>

        {!comp ? (
          <div className="overflow-y-auto pr-1 space-y-5 flex-1">
            {groupedComps.length === 0 && (
              <p className="text-xs text-muted-foreground italic py-10 text-center">
                Nenhuma competição com partida agendada para este filtro.
              </p>
            )}
            {groupedComps.map(g => (
              <div key={g.country} className="space-y-2.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-foreground flex items-center gap-1.5 uppercase tracking-wider font-mono">
                    {COUNTRY_FLAGS[g.country] && <span>{COUNTRY_FLAGS[g.country]}</span>}
                    {g.country}
                  </span>
                  <div className="flex-1 h-px bg-border/40"></div>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
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
                        className={`flex flex-col items-center justify-between gap-1.5 p-3 rounded-xl border transition-all text-center ${
                          empty
                            ? 'border-border/20 bg-muted/10 opacity-40 cursor-not-allowed'
                            : 'border-border/50 bg-muted/20 hover:border-emerald-500/50 hover:bg-accent/40 active:scale-[0.98] cursor-pointer'
                        }`}>
                        {logo ? (
                          <img src={logo} alt="" className="w-7 h-7 object-contain" loading="lazy" onError={onImgError} />
                        ) : (
                          <div className="w-7 h-7 rounded-full bg-muted/60 flex items-center justify-center text-xs font-bold text-muted-foreground">
                            ⚽
                          </div>
                        )}
                        <span className="text-[11px] font-semibold leading-snug line-clamp-2">{c.label}</span>
                        {empty ? (
                          <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-muted/50 text-muted-foreground font-mono">
                            Sem jogos
                          </span>
                        ) : (
                          <span className="text-[9.5px] font-mono font-bold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
                            {c.fixtures.length} {c.fixtures.length === 1 ? 'jogo' : 'jogos'}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex-1 flex flex-col space-y-3 overflow-hidden">
            <div className="flex items-center justify-between pb-2 border-b border-border/40">
              <button onClick={() => setComp('')} className="text-xs font-semibold text-emerald-400 hover:underline flex items-center gap-1 cursor-pointer">
                ← Voltar às competições
              </button>
              <span className="text-xs font-bold text-foreground font-mono bg-muted/40 px-2.5 py-1 rounded-lg border border-border/40">{comp}</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 overflow-y-auto pr-1 flex-1">
              {selectedMatches.length === 0 && <p className="text-xs text-muted-foreground italic col-span-full py-10 text-center">Nenhuma partida encontrada com os filtros.</p>}
              {selectedMatches.slice(0, 80).map(f => (
                <button key={f.fixture_id}
                  onClick={() => { onSelect(f); onOpenChange(false); }}
                  className="relative text-left p-3.5 rounded-xl border border-border/60 bg-muted/20 hover:border-emerald-500/50 hover:bg-accent/40 transition-all cursor-pointer group shadow-sm active:scale-[0.98]">
                  
                  {/* Badge H2H somente para Owner e Manager */}
                  {isOwnerOrManager && f.has_h2h && (
                    <div className="absolute -top-2 -right-2 z-10">
                      <H2HBadge />
                    </div>
                  )}

                  {/* Badge "Inicia em menos de 1 hora" centralizado acima do VS */}
                  {startsInLessThanHour(f.date) && (
                    <div className="absolute -top-2.5 left-1/2 -translate-x-1/2 z-10 pointer-events-none">
                      <StartingSoonBadge />
                    </div>
                  )}

                  <div className="flex items-center justify-between gap-2 mb-2 pt-1">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Flag name={f.home} ids={teamIds} />
                      <span className="text-xs font-bold truncate group-hover:text-emerald-400 transition-colors">{teamPt(f.home)}</span>
                    </div>
                    <span className="text-[10px] font-mono font-bold text-muted-foreground shrink-0">VS</span>
                    <div className="flex items-center gap-1.5 min-w-0 justify-end">
                      <span className="text-xs font-bold truncate group-hover:text-emerald-400 transition-colors">{teamPt(f.away)}</span>
                      <Flag name={f.away} ids={teamIds} />
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-[10.5px] text-muted-foreground pt-1.5 border-t border-border/30">
                    <span className="truncate">{competitionPt(f.league_name || f.tournament)}</span>
                    <span className="flex items-center gap-1 shrink-0 font-mono text-muted-foreground bg-muted/40 border border-border/40 px-2 py-0.5 rounded text-[10px]">
                      {isOldMatch(f.date) && <OldMatchBadge />}
                      <span>{fmtDateTime(f.date)}</span>
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

