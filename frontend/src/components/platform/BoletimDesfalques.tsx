"use client";
import { InjuriesResponse, InjuryPlayer, playerPhotoUrl, onImgError as hideOnError } from "@/lib/api";
import { teamPt } from "@/lib/teamNames";
import InfoTooltip from "@/components/platform/InfoTooltip";

// Tradução leve dos rótulos mais comuns da API-Football.
const REASON_PT: Record<string, string> = {
  "Missing Fixture": "Desfalque",
  "Questionable": "Dúvida",
  "Suspended": "Suspenso",
  "Injury": "Lesão",
  "Coach's decision": "Opção técnica",
  "National selection": "Convocação",
  "Rest": "Poupado",
};
function trReason(s: string | null): string {
  if (!s) return "Desfalque";
  return REASON_PT[s] || s
    .replace(/Injury/i, "Lesão").replace(/Muscle/i, "muscular")
    .replace(/Hamstring/i, "posterior da coxa").replace(/Calf/i, "panturrilha")
    .replace(/Knee/i, "joelho").replace(/Ankle/i, "tornozelo").replace(/Thigh/i, "coxa")
    .replace(/Knock/i, "pancada").replace(/Illness/i, "doença").replace(/Groin/i, "virilha")
    .replace(/Suspended/i, "Suspenso");
}
function isSuspension(p: InjuryPlayer): boolean {
  return /suspen|card|ban/i.test(`${p.type || ""} ${p.reason || ""}`);
}

function TeamColumn({ data, accent }: { data: InjuriesResponse; accent: string }) {
  const players = data.players || [];
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-semibold" style={{ color: accent }}>{teamPt(data.team)}</span>
        <span className="text-[11px] text-muted-foreground">{players.length} {players.length === 1 ? "desfalque" : "desfalques"}</span>
      </div>
      {players.length === 0 ? (
        <p className="text-xs text-muted-foreground italic py-2">Nenhum desfalque reportado. ✅</p>
      ) : (
        <ul className="space-y-1.5">
          {players.map((p, i) => (
            <li key={`${p.player_id}-${i}`} className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-muted overflow-hidden shrink-0">
                {playerPhotoUrl(p.player_id) && <img src={playerPhotoUrl(p.player_id)!} alt="" className="w-full h-full object-cover" loading="lazy" onError={hideOnError} />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium leading-tight truncate">{p.name}</p>
                <p className="text-[10px] text-muted-foreground truncate">{isSuspension(p) ? "🟥 " : "🚑 "}{trReason(p.reason)}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function BoletimDesfalques({ home, away }: {
  home: InjuriesResponse | null; away: InjuriesResponse | null;
}) {
  if (!home && !away) return null;
  return (
    <div className="bg-card border border-border/50 rounded-xl p-5">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        Boletim de Desfalques
        <InfoTooltip text="Jogadores fora ou em dúvida (lesão/suspensão) reportados pela API-Football para a temporada atual. Dados podem ser esparsos; ausência de registros não garante elenco completo." />
      </h3>
      <p className="text-xs text-muted-foreground mb-3">Lesões e suspensões reportadas</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
        {home && <TeamColumn data={home} accent="#10b981" />}
        {away && <TeamColumn data={away} accent="#f97316" />}
      </div>
    </div>
  );
}
