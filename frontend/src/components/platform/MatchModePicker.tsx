"use client";
import React, { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { MatchPickerModal, PickerFixture } from '@/components/platform/MatchPickerModal';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { api, UpcomingFixture } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';

type Mode = 'futura' | 'passada' | 'independente';

// Seletor de modo reutilizável, alinhado ao design da página Análise (Configuração do
// Confronto): a Análise Independente traz a grade completa (mandante/visitante/competição/
// campo neutro/árbitro). "Passada" é exclusivo da Estatística (só aparece com onSelectPast).
export function MatchModePicker({
  onSelectPast,
  onSelectFuture,
  onModeChange,
  onRefereeChange,
}: {
  showReferee?: boolean;
  onSelectPast?: (fx: PickerFixture) => void;
  onSelectFuture?: (fx: PickerFixture) => void;
  onModeChange?: (m: Mode) => void;
  onRefereeChange?: (r: string) => void;
}) {
  const {
    homeTeamId, setHomeTeamId, awayTeamId, setAwayTeamId,
    competition, setCompetition, neutralField, setNeutralField,
  } = usePrediction();
  const [mode, setModeState] = useState<Mode>('independente');
  const setMode = (m: Mode) => { setModeState(m); onModeChange?.(m); };
  const [referee, setReferee] = useState('');
  const [referees, setReferees] = useState<string[]>([]);
  const [teams, setTeams] = useState<string[]>([]);
  const [tournaments, setTournaments] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [past, setPast] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [futureOpen, setFutureOpen] = useState(false);
  const [pastOpen, setPastOpen] = useState(false);

  React.useEffect(() => {
    api.upcomingFixtures().then(r => setUpcoming(r.fixtures)).catch(() => {});
    api.teamIds().then(setTeamIds).catch(() => {});
    api.referees().then(r => setReferees(r.referees)).catch(() => {});
    api.teams().then(r => { setTeams(r.teams); setTournaments(r.tournaments); }).catch(() => {});
    if (onSelectPast) api.pastFixtures().then(r => setPast(r.fixtures)).catch(() => {});
  }, [onSelectPast]);

  const pickFuture = (fx: PickerFixture) => {
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    if (fx.tournament) setCompetition(fx.tournament);
    setNeutralField(!!fx.neutral);
    onSelectFuture?.(fx);
  };

  const changeReferee = (r: string) => { setReferee(r); onRefereeChange?.(r); };

  const tabCls = (m: Mode) =>
    `px-3 py-1.5 rounded-md transition-colors ${mode === m ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`;

  return (
    <div className="mb-2">
      <div className="inline-flex p-1 mb-4 rounded-lg bg-muted text-xs font-medium flex-wrap items-center">
        <button onClick={() => setMode('futura')} className={tabCls('futura')}>Selecionar Partida Agendada</button>
        {onSelectPast && <button onClick={() => setMode('passada')} className={tabCls('passada')}>Selecionar Partida Passada</button>}
        <button onClick={() => { setMode('independente'); }} className={tabCls('independente')}>Análise Independente</button>
        <InfoTooltip text="Selecionar Partida Agendada: pré-preenche as equipes de um jogo marcado. Selecionar Partida Passada: abre as estatísticas completas de um jogo já disputado. Análise Independente: escolha duas equipes quaisquer para comparar." />
      </div>

      {mode === 'futura' && (
        <div className="mb-2">
          <button onClick={() => setFutureOpen(true)}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors">
            {homeTeamId && awayTeamId ? `${teamPt(homeTeamId)} x ${teamPt(awayTeamId)} — trocar partida` : 'Escolher partida agendada'}
          </button>
          {homeTeamId && awayTeamId && (
            <p className="text-[11px] text-muted-foreground mt-2">Competição: {competition} · {neutralField ? 'Campo neutro' : 'Com mando'}</p>
          )}
        </div>
      )}

      {mode === 'passada' && onSelectPast && (
        <div className="mb-2">
          <button onClick={() => setPastOpen(true)}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors">
            {homeTeamId && awayTeamId ? `${teamPt(homeTeamId)} x ${teamPt(awayTeamId)} — trocar partida` : 'Escolher partida passada'}
          </button>
          <p className="text-[11px] text-muted-foreground mt-1.5">Abre as estatísticas completas de um jogo já disputado.</p>
        </div>
      )}

      {mode === 'independente' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Mandante</Label>
            <TeamSelect value={homeTeamId} onValueChange={setHomeTeamId} teams={teams.filter(t => t !== awayTeamId)} />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Time Visitante</Label>
            <TeamSelect value={awayTeamId} onValueChange={setAwayTeamId} teams={teams.filter(t => t !== homeTeamId)} />
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block">Competição</Label>
            <Select value={competition} onValueChange={setCompetition}>
              <SelectTrigger className="h-10"><SelectValue placeholder="Selecione..." /></SelectTrigger>
              <SelectContent>{tournaments.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div>
            <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">
              Árbitro (opcional)
              <InfoTooltip text="Informe o árbitro da partida para habilitar o card Fator Árbitro (perfil disciplinar). Não altera os demais cálculos." />
            </Label>
            <TeamSelect value={referee} onValueChange={changeReferee} teams={referees} labelFn={(s) => s} placeholder="Buscar árbitro..." searchPlaceholder="Buscar árbitro..." />
          </div>
          <div className="flex items-end pb-2">
            <div className="flex items-center gap-2">
              <Switch id="neutral-stats" checked={neutralField} onCheckedChange={setNeutralField} />
              <Label htmlFor="neutral-stats" className="text-sm cursor-pointer">Campo Neutro</Label>
              <InfoTooltip text="Remove a vantagem de mando de campo das projeções." />
            </div>
          </div>
        </div>
      )}

      <MatchPickerModal open={futureOpen} onOpenChange={setFutureOpen} fixtures={upcoming} teamIds={teamIds} onSelect={pickFuture} title="Selecionar Partida Agendada" />
      {onSelectPast && (
        <MatchPickerModal open={pastOpen} onOpenChange={setPastOpen} fixtures={past} teamIds={teamIds} onSelect={onSelectPast} title="Selecionar Partida Passada" />
      )}
    </div>
  );
}
