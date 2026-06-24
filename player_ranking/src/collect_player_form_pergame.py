#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
player_ranking/src/collect_player_form_pergame.py
=================================================
Coleta POINT-IN-TIME da FORMA RECENTE DE CLUBE dos jogadores convocados, por jogo —
a hipótese ortogonal ao Elo que ficou em aberto (ver player_ranking/RELATORIO.md §8-9).

Para cada jogo-alvo (data D) e cada jogador do elenco-base leakage-safe, resolve o
clube (via /players, tentando a temporada europeia de D e a anterior — robusto a ligas
de ano-calendário), pega os fixtures de clube em [D-120d, D), e extrai por jogo:
  - rating + minutos do jogador (forma e carga),
  - xG/xGA do TIME do jogador naquele jogo de clube (momento ofensivo/defensivo).
Agrega por seleção: forma média recente, carga (fadiga), jogos em 30d, tendência,
xG a favor/contra do bloco de clubes, e cobertura.
Além disso mede DISPONIBILIDADE: quantos do elenco-base estavam afastados (lesão/
suspensão) na data D, via /sidelined (histórico com início/fim — point-in-time safe).

Tudo via ApiClient (cache em disco, rate-limit, RETOMADA, teto de cota). RESUMÁVEL:
re-rodar continua de onde parou (pula jogos já feitos e chamadas já cacheadas). Ao
atingir o teto de cota, salva o progresso e sai — basta re-rodar no dia seguinte.
Ordem de processamento: dos jogos MAIS RECENTES aos mais antigos.

NÃO toca produção. Saída: player_ranking/data/processed/pergame_form.parquet
(uma linha por jogo-alvo, pronta para o gate Elo vs Elo+forma).
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "player_ranking" / "src"))
from apiclient import ApiClient, BudgetExhausted

INTERIM = ROOT / "player_ranking" / "data" / "interim"
PROC = ROOT / "player_ranking" / "data" / "processed"
TARGETS = INTERIM / "target_matches_recent.parquet"
OUT = PROC / "pergame_form.parquet"
CSV = ROOT / "international_features_enriched_apifootball.csv"

K_RECENT = 6          # últimas K partidas de clube antes de D
WINDOW_DAYS = 120     # janela de forma recente
MAX_REQUESTS = 45000  # teto por execução (margem sob a cota diária ja parcialmente usada)


def european_seasons(d: pd.Timestamp):
    """Temporadas api-football candidatas que contêm [D-120d, D)."""
    y = d.year
    cands = {y, y - 1}
    if (d - timedelta(days=WINDOW_DAYS)).year not in cands:
        cands.add((d - timedelta(days=WINDOW_DAYS)).year)
    return sorted(cands, reverse=True)


def resolve_club(cli, pid, seasons):
    """Retorna (club_id, season_usada) do clube com mais jogos, tentando as temporadas."""
    best = None
    for s in seasons:
        prof = cli.get("/players", f"prof/{pid}_{s}", id=pid, season=s)
        for st in (prof[0].get("statistics", []) if prof else []):
            team = st.get("team", {})
            if not team.get("id"):
                continue
            apps = (st.get("games", {}) or {}).get("appearences") or 0
            if best is None or apps > best[2]:
                best = (team["id"], s, apps)
    return (best[0], best[1]) if best else (None, None)


def club_fixtures_before(cli, club_id, seasons, D):
    """Fixtures de clube (id, date) em [D-120d, D), ordenados por data."""
    lo = (D - timedelta(days=WINDOW_DAYS)).isoformat()
    hi = D.isoformat()
    out = []
    for s in seasons:
        fx = cli.get("/fixtures", f"clubfx/{club_id}_{s}", team=club_id, season=s)
        for f in fx:
            dt = f.get("fixture", {}).get("date", "")
            if lo <= dt < hi and f.get("fixture", {}).get("id"):
                out.append((f["fixture"]["id"], dt))
    out = sorted(set(out), key=lambda x: x[1])
    return out[-K_RECENT:]


def club_match_xg(cli, fid, club_id):
    """xG (a favor, contra) do time club_id no fixture fid. (None,None) se ausente."""
    st = cli.get("/fixtures/statistics", f"fxst/{fid}", fixture=fid)
    xg_for = xg_against = None
    for team in st:
        is_self = (team.get("team", {}) or {}).get("id") == club_id
        for s in (team.get("statistics") or []):
            if "xpected" in str(s.get("type", "")):
                v = s.get("value")
                if v not in (None, ""):
                    try:
                        fv = float(v)
                    except (TypeError, ValueError):
                        continue
                    if is_self:
                        xg_for = fv
                    else:
                        xg_against = fv
    return xg_for, xg_against


def player_form(cli, pid, club_id, club_fixtures):
    """Extrai (rating, minutos, datas) de pid e xG/xGA do clube nas partidas dadas."""
    ratings, minutes, dates, xgf, xga = [], [], [], [], []
    for fid, dt in club_fixtures:
        fp = cli.get("/fixtures/players", f"fxpl/{fid}", fixture=fid)
        appeared = False
        for team in fp:
            for pl in team.get("players", []):
                if pl.get("player", {}).get("id") == pid:
                    st = (pl.get("statistics") or [{}])[0]
                    g = st.get("games", {}) or {}
                    r, m = g.get("rating"), g.get("minutes")
                    if r is not None:
                        ratings.append(float(r))
                    minutes.append(int(m) if m else 0)
                    dates.append(dt)
                    appeared = True
        if appeared:
            xf, xa = club_match_xg(cli, fid, club_id)
            if xf is not None:
                xgf.append(xf)
            if xa is not None:
                xga.append(xa)
    return ratings, minutes, dates, xgf, xga


def player_sidelined_at(cli, pid, D_iso):
    """True se pid tinha um período de afastamento (lesão/suspensão) cobrindo D."""
    sl = cli.get("/sidelined", f"sdl/{pid}", player=pid)
    for period in sl or []:
        s, e = period.get("start"), period.get("end")
        if s and e and s <= D_iso <= e:
            return True
    return False


def squad_features(cli, pids, D, seasons):
    """Agrega forma da seleção (forma/carga/xG) + disponibilidade a partir do elenco-base."""
    rats, mins_load, games30, trends = [], [], [], []
    xgf_team, xga_team = [], []
    n_cov = n_xg_cov = unavail = 0
    cutoff30 = (D - timedelta(days=30)).isoformat()
    D_iso = D.isoformat()
    for pid in pids:
        # disponibilidade (1 chamada por jogador, cacheada entre jogos)
        if player_sidelined_at(cli, pid, D_iso):
            unavail += 1
        club_id, s_used = resolve_club(cli, pid, seasons)
        if not club_id:
            continue
        cf = club_fixtures_before(cli, club_id, seasons, D)
        if not cf:
            continue
        ratings, minutes, dates, xgf, xga = player_form(cli, pid, club_id, cf)
        if not ratings:
            continue
        n_cov += 1
        rats.append(np.mean(ratings))
        mins_load.append(np.mean(minutes) if minutes else 0)
        games30.append(sum(1 for d in dates if d >= cutoff30))
        trends.append(ratings[-1] - np.mean(ratings[:-1]) if len(ratings) > 1 else 0.0)
        if xgf:
            xgf_team.append(np.mean(xgf))
        if xga:
            xga_team.append(np.mean(xga))
            n_xg_cov += 1
    if n_cov == 0:
        return None
    out = {
        "form_rating": float(np.mean(rats)),
        "form_minutes": float(np.mean(mins_load)),
        "form_games30": float(np.mean(games30)),
        "form_trend": float(np.mean(trends)),
        "coverage": n_cov / max(1, len(pids)),
        "unavail_count": float(unavail),
        "unavail_rate": unavail / max(1, len(pids)),
        "xg_coverage": n_xg_cov / max(1, len(pids)),
        "form_xg_for": float(np.mean(xgf_team)) if xgf_team else np.nan,
        "form_xg_against": float(np.mean(xga_team)) if xga_team else np.nan,
    }
    return out


def main():
    t = pd.read_parquet(TARGETS)
    df = pd.read_csv(CSV, parse_dates=["date"])
    elo = df.set_index("match_id")["elo_diff"].to_dict()

    done_ids = set()
    if OUT.exists():
        prev = pd.read_parquet(OUT)
        done_ids = set(prev["match_id"].tolist())
        print(f"retomando: {len(done_ids)} jogos ja processados")
    rows = [] if not OUT.exists() else pd.read_parquet(OUT).to_dict("records")

    cli = ApiClient(max_requests=MAX_REQUESTS)
    # MAIS RECENTES primeiro (preferência do usuário: garantir os jogos atuais)
    t = t.sort_values("date", ascending=False)
    processed = 0
    diff_keys = ("form_rating", "form_minutes", "form_games30", "form_trend",
                 "form_xg_for", "form_xg_against", "unavail_rate")
    try:
        for _, r in t.iterrows():
            if r["match_id"] in done_ids:
                continue
            D = pd.to_datetime(r["date"])
            seasons = european_seasons(D)
            hf = squad_features(cli, list(r["home_pids"]), D, seasons)
            af = squad_features(cli, list(r["away_pids"]), D, seasons)
            row = {"match_id": r["match_id"], "date": r["date"],
                   "home_team": r["home_team"], "away_team": r["away_team"],
                   "result": r["result"], "elo_diff": elo.get(r["match_id"], np.nan)}
            for side, f in [("home", hf), ("away", af)]:
                if f:
                    for k, v in f.items():
                        row[f"{side}_{k}"] = v
            if hf and af:
                for k in diff_keys:
                    if k in hf and k in af and pd.notna(hf[k]) and pd.notna(af[k]):
                        row[f"diff_{k}"] = hf[k] - af[k]
            rows.append(row)
            processed += 1
            if processed % 25 == 0:
                pd.DataFrame(rows).to_parquet(OUT)
                print(f"  {processed} novos | cota usada {cli.n_live} | restante {cli.remaining}")
    except BudgetExhausted as e:
        print(f"[TETO] {e} — salvando progresso e saindo (re-rode amanha para continuar).")
    finally:
        PROC.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(OUT)
        tot = len(rows)
        print(f"\nSalvo {OUT} | total jogos com forma: {tot} | novos nesta run: {processed}")
        print(f"requests: {cli.stats()}")
        print(f"faltam ~{len(t) - tot} jogos (re-rode para continuar)")


if __name__ == "__main__":
    main()
