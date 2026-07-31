"use client";
import React from 'react';
import { teamLogoUrl, onImgError } from '@/lib/api';
import { teamPt } from '@/lib/teamNames';
import { Edit3 } from 'lucide-react';

function fmtDateTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())} · ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
}

const Side = ({ name, id, role, align }: { name: string; id?: number; role: string; align: 'left' | 'right' }) => {
  const url = teamLogoUrl(id);
  return (
    <div className={`flex items-center gap-2.5 min-w-0 ${align === 'right' ? 'flex-row-reverse text-right' : ''}`}>
      {url && <img src={url} alt="" className="w-8 h-8 sm:w-9 sm:h-9 object-contain shrink-0 drop-shadow-md" loading="lazy" onError={onImgError} />}
      <div className="min-w-0">
        <p className="text-sm sm:text-base font-bold text-foreground truncate tracking-tight">{teamPt(name)}</p>
        <p className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">{role}</p>
      </div>
    </div>
  );
};

export function MatchHeader({
  home, away, teamIds, competition, date, venue, referee, neutral, onEditTeams,
}: {
  home: string; away: string; teamIds: Record<string, number>;
  competition?: string; date?: string; venue?: string | null; referee?: string | null; neutral?: boolean;
  onEditTeams?: () => void;
}) {
  const [isScrolled, setIsScrolled] = React.useState(false);

  React.useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 80);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  if (!home || !away) return null;
  const meta = [
    competition,
    fmtDateTime(date),
    venue ? `🏟️ ${venue}` : '',
    typeof neutral === 'boolean' ? (neutral ? 'Campo neutro' : (venue ? '' : 'Com mando')) : '',
    referee ? `👨‍⚖️ ${referee}` : '',
  ].filter(Boolean);

  const handleEdit = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (onEditTeams) onEditTeams();
  };

  return (
    <>
      {/* Mobile reduced floating balloon (scrolled) */}
      {isScrolled && (
        <div className="md:hidden fixed top-2.5 left-1/2 -translate-x-1/2 z-[60] pointer-events-auto">
          <div
            onClick={handleEdit}
            className="cursor-pointer flex flex-col items-center bg-card/95 backdrop-blur-xl border border-emerald-500/40 hover:border-emerald-500/60 rounded-xl px-3 py-1.5 shadow-xl shadow-black/50 active:scale-[0.95] transition-all"
          >
            <Edit3 className="w-3 h-3 text-emerald-400 mb-0.5" />
            <div className="flex items-center gap-2">
              {teamLogoUrl(teamIds[home]) ? (
                <div className="w-7 h-7 flex items-center justify-center bg-muted/30 rounded overflow-hidden shrink-0 border border-border/20">
                  <img src={teamLogoUrl(teamIds[home])!} alt="" className="max-w-full max-h-full object-contain" onError={onImgError} />
                </div>
              ) : (
                <div className="w-7 h-7 bg-muted/30 rounded shrink-0" />
              )}
              <span className="text-[10px] font-extrabold text-muted-foreground uppercase">x</span>
              {teamLogoUrl(teamIds[away]) ? (
                <div className="w-7 h-7 flex items-center justify-center bg-muted/30 rounded overflow-hidden shrink-0 border border-border/20">
                  <img src={teamLogoUrl(teamIds[away])!} alt="" className="max-w-full max-h-full object-contain" onError={onImgError} />
                </div>
              ) : (
                <div className="w-7 h-7 bg-muted/30 rounded shrink-0" />
              )}
            </div>
          </div>
        </div>
      )}

      {/* Main header block */}
      <div className={`sticky top-16 z-30 space-y-1.5 pointer-events-none ${isScrolled ? 'hidden md:block' : ''}`}>
        {onEditTeams && (
          <div className="flex justify-center pointer-events-auto">
            <button
              onClick={handleEdit}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground bg-card/90 backdrop-blur-xl border border-emerald-500/30 hover:border-emerald-500/60 rounded-full px-3.5 py-1.5 shadow-lg shadow-black/40 transition-all cursor-pointer active:scale-[0.97]"
            >
              <Edit3 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Alterar Confronto</span>
            </button>
          </div>
        )}
        <div className="pointer-events-auto relative mx-auto w-full sm:max-w-md md:max-w-lg lg:max-w-xl bg-card/90 backdrop-blur-xl border border-border/70 rounded-2xl px-5 py-3 shadow-xl shadow-black/30">
          <div className="flex items-center justify-between gap-4">
            <div className="flex-1 min-w-0"><Side name={home} id={teamIds[home]} role="Mandante" align="right" /></div>
            <div className="shrink-0 flex items-center justify-center w-7 h-7 rounded-full bg-muted/50 border border-border/50 text-[11px] font-mono font-bold text-muted-foreground">
              VS
            </div>
            <div className="flex-1 min-w-0"><Side name={away} id={teamIds[away]} role="Visitante" align="left" /></div>
          </div>
          {meta.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-x-2.5 gap-y-0.5 text-[11px] font-medium text-muted-foreground mt-2 pt-2 border-t border-border/40">
              {meta.map((m, i) => (
                <React.Fragment key={i}>
                  {i > 0 && <span className="text-border">•</span>}
                  <span>{m}</span>
                </React.Fragment>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

