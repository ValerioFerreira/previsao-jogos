"use client";
import React, { useState } from 'react';
import { Label } from '@/components/ui/label';
import { TeamSelect } from '@/components/platform/TeamSelect';
import { MatchPickerModal, PickerFixture } from '@/components/platform/MatchPickerModal';
import InfoTooltip from '@/components/platform/InfoTooltip';
import { usePrediction } from '@/lib/PredictionContext';
import { api, UpcomingFixture } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';

type Mode = 'futura' | 'passada' | 'independente';

// Seletor de modo reutilizável. Futura/Passada usam o MESMO modal (MatchPickerModal),
// igual à aba Previsões. "Passada" só aparece se onSelectPast for fornecido.
export function MatchModePicker({
  showReferee = true,
  onSelectPast,
  onModeChange,
}: {
  showReferee?: boolean;
  onSelectPast?: (fx: PickerFixture) => void;
  onModeChange?: (m: Mode) => void;
}) {
  const { setHomeTeamId, setAwayTeamId, setCompetition, setNeutralField } = usePrediction();
  const [mode, setModeState] = useState<Mode>('independente');
  const setMode = (m: Mode) => { setModeState(m); onModeChange?.(m); };
  const [referee, setReferee] = useState('');
  const [referees, setReferees] = useState<string[]>([]);
  const [upcoming, setUpcoming] = useState<UpcomingFixture[]>([]);
  const [past, setPast] = useState<UpcomingFixture[]>([]);
  const [teamIds, setTeamIds] = useState<Record<string, number>>({});
  const [futureOpen, setFutureOpen] = useState(false);
  const [pastOpen, setPastOpen] = useState(false);

  React.useEffect(() => {
    api.upcomingFixtures().then(r => setUpcoming(r.fixtures)).catch(() => {});
    api.teamIds().then(setTeamIds).catch(() => {});
    if (showReferee) api.referees().then(r => setReferees(r.referees)).catch(() => {});
    if (onSelectPast) api.pastFixtures().then(r => setPast(r.fixtures)).catch(() => {});
  }, [showReferee, onSelectPast]);

  const pickFuture = (fx: PickerFixture) => {
    setHomeTeamId(fx.home);
    setAwayTeamId(fx.away);
    if (fx.tournament) setCompetition(fx.tournament);
    setNeutralField(!!fx.neutral);
  };

  const tabCls = (m: Mode) =>
    `px-3 py-1.5 rounded-md transition-colors ${mode === m ? 'bg-background shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`;

  return (
    <div className="mb-2">
      <div className="inline-flex p-1 mb-3 rounded-lg bg-muted text-xs font-medium flex-wrap">
        <button onClick={() => setMode('futura')} className={tabCls('futura')}>Selecionar Partida Futura</button>
        {onSelectPast && <button onClick={() => setMode('passada')} className={tabCls('passada')}>Selecionar Partida Passada</button>}
        <button onClick={() => setMode('independente')} className={tabCls('independente')}>Análise Independente</button>
      </div>

      {mode === 'futura' && (
        <div className="mb-3">
          <button onClick={() => setFutureOpen(true)}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors">
            Escolher partida agendada
          </button>
          <p className="text-[11px] text-muted-foreground mt-1.5">Pré-preenche as equipes (e competição/mando) abaixo.</p>
        </div>
      )}

      {mode === 'passada' && onSelectPast && (
        <div className="mb-3">
          <button onClick={() => setPastOpen(true)}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-cyan-500/40 bg-cyan-500/10 text-foreground hover:bg-cyan-500/20 transition-colors">
            Escolher partida passada
          </button>
          <p className="text-[11px] text-muted-foreground mt-1.5">Abre as estatísticas completas de um jogo já disputado.</p>
        </div>
      )}

      {showReferee && mode === 'independente' && (
        <div className="max-w-xs">
          <Label className="text-xs text-muted-foreground mb-1.5 block flex items-center gap-1">
            Árbitro (opcional)
            <InfoTooltip text="Você pode informar o árbitro. No momento não influencia os cálculos; ficará disponível para análises futuras." />
          </Label>
          <TeamSelect value={referee} onValueChange={setReferee} teams={referees} labelFn={(s) => s} placeholder="Buscar árbitro..." searchPlaceholder="Buscar árbitro..." />
        </div>
      )}

      <MatchPickerModal open={futureOpen} onOpenChange={setFutureOpen} fixtures={upcoming} teamIds={teamIds} onSelect={pickFuture} title="Selecionar Partida Futura" />
      {onSelectPast && (
        <MatchPickerModal open={pastOpen} onOpenChange={setPastOpen} fixtures={past} teamIds={teamIds} onSelect={onSelectPast} title="Selecionar Partida Passada" />
      )}
    </div>
  );
}
