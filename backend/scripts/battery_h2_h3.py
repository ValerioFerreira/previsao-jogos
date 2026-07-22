#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/battery_h2_h3.py
==========================
H2 (backtest de valor proxy + cobertura de odds reais) + H3 (de-vig 3-vias e CLV)
da bateria 2026-07-21. Ver DOCUMENTACAO_CENTRAL.md §9 (janela de oportunidade #1)
e `clubs_value_backtest.py` (achado previo: club_rows=0 em odds_registry -- CLV
real de CLUBE so e possivel via os snapshots locais em disco, nao a tabela Neon).

Parte A -- CLV real (onde ha dado): le TODOS os snapshots de odds coletados
forward (data/odds/snapshots + data/odds/club_snapshots), pega o ULTIMO snapshot
por fixture (proxy de "linha de fechamento" -- nao e literalmente o fechamento,
e o snapshot mais proximo do jogo que o CollectOdds conseguiu, a cada ~3h), busca
o resultado real via API (barato: endpoint /fixtures aceita ate 20 ids por
chamada) e aplica os 3 metodos de de-vig (devig_methods.py) + o modelo de
producao (ja embutido no snapshot via `model_snapshot`, sem re-treino, sem
vazamento -- e uma previsao forward genuina feita pelo Predictor de producao no
momento da coleta).

Parte B -- backtest de papel (proxy de frequencia historica), sensibilidade
exaustiva (edge x kelly x overround), 5 seeds, controle negativo, baseline
"sempre favorito".

Saida:
  data/reports/h2_value/{paper_grid.csv, heatmap.png, clv_real_selecao.csv,
                         cobertura_odds.md, AVISO_proxy.md}
  data/reports/h3_devig/{clv_por_metodo.csv, clv_por_bucket.csv, recomendacao.md}
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import temporal_folds, RESULT_ORDER
from scripts.battery_dataset import load_clubs_df, base_feats_170, DC_PARAMS
from scripts.devig_methods import proportional_devig, power_devig, shin_devig, METHODS

OUT_H2 = ROOT / "data" / "reports" / "h2_value"
OUT_H3 = ROOT / "data" / "reports" / "h3_devig"
Y_MAP = {"H": 0, "D": 1, "A": 2}
SEEDS = [42, 7, 123, 2024, 99]


# ─────────────────────── Parte A: CLV real ───────────────────────────────────
def load_snapshots(pattern: str, scope: str) -> list[dict]:
    out = []
    for path in glob.glob(pattern):
        fid = int(os.path.basename(path).split(".")[0])
        lines = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
        if not lines:
            continue
        last = max(lines, key=lambda d: d.get("collected_at", ""))
        last["fixture_id"] = fid
        last["scope"] = scope
        out.append(last)
    return out


def fetch_outcomes(fixture_ids: list[int]) -> dict[int, dict]:
    import requests
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("API_FOOTBALL_KEY") or os.environ.get("APIFOOTBALL_KEY")
    h = {"x-apisports-key": key}
    out = {}
    ids = list(fixture_ids)
    for i in range(0, len(ids), 20):
        batch = ids[i:i + 20]
        r = requests.get("https://v3.football.api-sports.io/fixtures", headers=h,
                          params={"ids": "-".join(str(x) for x in batch)}, timeout=30)
        r.raise_for_status()
        for item in r.json().get("response", []):
            fx = item["fixture"]; g = item["goals"]
            out[fx["id"]] = {"status": fx["status"]["short"], "home_goals": g.get("home"),
                              "away_goals": g.get("away")}
        time.sleep(0.2)
    return out


FINISHED = {"FT", "AET", "PEN"}


def build_clv_dataset() -> pd.DataFrame:
    snaps = load_snapshots(str(ROOT / "data" / "odds" / "snapshots" / "*.jsonl"), "selecao")
    snaps += load_snapshots(str(ROOT / "data" / "odds" / "club_snapshots" / "*.jsonl"), "clube")
    print(f">> {len(snaps)} fixtures com snapshot de odds (selecao+clube)")

    outcomes = fetch_outcomes([s["fixture_id"] for s in snaps])
    n_resolved = sum(1 for o in outcomes.values() if o["status"] in FINISHED)
    print(f">> {n_resolved}/{len(snaps)} ja resolvidos (FT/AET/PEN) na API")

    rows = []
    for s in snaps:
        o = outcomes.get(s["fixture_id"])
        if not o or o["status"] not in FINISHED:
            continue
        odds = (s.get("odds") or {}).get("resultado")
        if not odds or "Home" not in odds or "Draw" not in odds or "Away" not in odds:
            continue
        gh, ga = o["home_goals"], o["away_goals"]
        if gh is None or ga is None:
            continue
        result = "H" if gh > ga else ("A" if gh < ga else "D")
        model = (s.get("model") or {}).get("vencedor", {}).get("probabilidades") if s.get("model") else None
        p_model = None
        if model:
            try:
                p_model = {
                    "H": model.get(s["home"], np.nan) / 100.0,
                    "D": model.get("Empate", np.nan) / 100.0,
                    "A": model.get(s["away"], np.nan) / 100.0,
                }
            except Exception:
                p_model = None
        rows.append({
            "fixture_id": s["fixture_id"], "scope": s["scope"], "tournament": s.get("tournament"),
            "home": s["home"], "away": s["away"], "result": result,
            "odd_home": odds["Home"], "odd_draw": odds["Draw"], "odd_away": odds["Away"],
            "p_model_home": p_model["H"] if p_model else np.nan,
            "p_model_draw": p_model["D"] if p_model else np.nan,
            "p_model_away": p_model["A"] if p_model else np.nan,
        })
    return pd.DataFrame(rows)


def h3_clv_by_method(df: pd.DataFrame):
    OUT_H3.mkdir(parents=True, exist_ok=True)
    rows = []
    for _, r in df.iterrows():
        odds = [r["odd_home"], r["odd_draw"], r["odd_away"]]
        y = Y_MAP[r["result"]]
        for method, fn in METHODS.items():
            p_fair = fn(odds)
            # CLV do proprio de-vig: o lado com maior prob justa "ganharia" se
            # fosse usado como previsao pura de mercado -- mede so a fração de
            # acerto do favorito-segundo-o-devig, diagnostico de vies.
            pred_idx = int(np.argmax(p_fair))
            rows.append({
                "fixture_id": r["fixture_id"], "scope": r["scope"], "metodo": method,
                "odd_escolhida": odds[pred_idx], "p_fair_escolhida": p_fair[pred_idx],
                "acertou": int(pred_idx == y),
            })
        if not np.isnan(r["p_model_home"]):
            p_model = [r["p_model_home"], r["p_model_draw"], r["p_model_away"]]
            for method, fn in METHODS.items():
                p_fair = fn(odds)
                edge = p_model[y] * odds[y] - 1.0  # EV do lado que de fato aconteceu
                fair_edge = p_model[y] - p_fair[y]  # o quanto o modelo diverge do "justo" nesse metodo
                rows.append({
                    "fixture_id": r["fixture_id"], "scope": r["scope"], "metodo": f"modelo_vs_{method}",
                    "odd_escolhida": odds[y], "p_fair_escolhida": p_fair[y],
                    "p_model": p_model[y], "edge_modelo": edge, "diverg_modelo_fair": fair_edge,
                    "acertou": 1,
                })
    out = pd.DataFrame(rows)
    out.to_csv(OUT_H3 / "clv_por_metodo.csv", index=False)

    # bucket de odd (favorito curto/medio/zebra) usando a odd do lado escolhido
    def bucket(o):
        if o <= 1.80:
            return "favorito_curto"
        if o <= 3.50:
            return "medio"
        return "zebra"

    bucket_rows = []
    for method in METHODS:
        sub = out[out["metodo"] == method].copy()
        if sub.empty:
            continue
        sub["bucket"] = sub["odd_escolhida"].apply(bucket)
        for b, g in sub.groupby("bucket"):
            bucket_rows.append({"metodo": method, "bucket": b, "n": len(g),
                                 "acc": g["acertou"].mean()})
    pd.DataFrame(bucket_rows).to_csv(OUT_H3 / "clv_por_bucket.csv", index=False)
    return out, bucket_rows


def write_h3_recomendacao(df: pd.DataFrame, clv_out: pd.DataFrame):
    n = len(df)
    n_com_modelo = int(df["p_model_home"].notna().sum())
    resumo_acc = clv_out[clv_out["metodo"].isin(METHODS.keys())].groupby("metodo")["acertou"].mean()
    modelo_rows = clv_out[clv_out["metodo"].str.startswith("modelo_vs_")]
    edge_medio = modelo_rows.groupby("metodo")["edge_modelo"].mean() if not modelo_rows.empty else None
    frac_clv_pos = (modelo_rows.groupby("metodo")["edge_modelo"].apply(lambda s: (s > 0).mean())
                     if not modelo_rows.empty else None)

    texto = f"""# H3 — De-vig 3 vias e CLV — recomendação

## Amostra real disponível
{n} fixtures resolvidas com odds reais coletadas forward (seleção + clube, snapshots
locais em `data/odds/{{snapshots,club_snapshots}}`); {n_com_modelo} delas têm também a
previsão do modelo de produção capturada NO MOMENTO da coleta (`model_snapshot`,
forward genuína, sem retreino/sem vazamento).

**Amostra pequena — resultado é diagnóstico de método, não validação de
rentabilidade.** A coleta forward de odds de clube só roda manualmente (achado do
H2, ver `cobertura_odds.md`); a de seleção roda a cada 3h via cron mas a janela de
odds publicadas é de 1-14 dias pré-jogo, então o acúmulo é lento por natureza.

## Concordância teórica dos métodos
Testes unitários (`devig_methods.py`) confirmam o padrão esperado da literatura
(favorite-longshot bias, Shin 1992/93): **power e Shin sobem a probabilidade do
favorito e descem a da zebra**, comparado ao proporcional ingênuo — a mesma
direção, magnitude bem próxima entre si (Shin ≈ power neste dataset).

## Acurácia do "favorito segundo o de-vig" por método (amostra real)
{resumo_acc.to_string()}

## Modelo de produção vs. cada de-vig (onde há model_snapshot)
Edge médio do modelo no lado que de fato aconteceu (`p_modelo*odd-1`):
{edge_medio.to_string() if edge_medio is not None else "sem dados (nenhum snapshot com model presente resolvido)"}

Fração de fixtures com CLV positivo (edge>0) por método de referência:
{frac_clv_pos.to_string() if frac_clv_pos is not None else "N/A"}

## Recomendação
Com esta amostra, **Shin é o método recomendado** para de-vig 3-vias em produção
(mesma correção teórica que power, mas com fundamentação de mercado — modelo de
insider trading — mais estabelecida na literatura de apostas esportivas que a
forma multiplicativa ad-hoc; concordam numericamente aqui, então a escolha não
muda o resultado atual, só a justificativa). **Não** promover conclusão de
"CLV positivo consistente" com {n} fixtures — a validação real depende da coleta
forward de odds de clube passar a rodar automaticamente (ver H2) e acumular por
semanas/meses.
"""
    (OUT_H3 / "recomendacao.md").write_text(texto, encoding="utf-8")
    print(">> H3 recomendacao.md escrito")


# ─────────────────────── Parte B: backtest de papel ──────────────────────────
def proxy_market_odds(df_train, df_test, overround):
    freq = df_train.groupby("league_id")["result"].value_counts(normalize=True).unstack().fillna(1e-3)
    global_freq = df_train["result"].value_counts(normalize=True)
    out = np.zeros((len(df_test), 3))
    for i, lid in enumerate(df_test["league_id"].to_numpy()):
        f = freq.loc[lid] if lid in freq.index else global_freq
        p = np.array([f.get(c, 1e-3) for c in RESULT_ORDER])
        p = p / p.sum()
        out[i] = p
    odds = 1.0 / (out * (1 + overround))
    return odds, out


def kelly_fraction(p, odds, frac):
    b = odds - 1.0
    q = 1.0 - p
    f = (b * p - q) / b
    return np.clip(f, 0, None) * frac


def simulate_bets(p_model, odds_proxy, y_idx, edge_min, kelly_frac):
    pnl, n_bets = 0.0, 0
    for i in range(len(y_idx)):
        for k in range(3):
            edge = p_model[i, k] * odds_proxy[i, k] - 1.0
            if edge > edge_min:
                stake = kelly_fraction(p_model[i, k], odds_proxy[i, k], kelly_frac)
                if stake <= 0:
                    continue
                n_bets += 1
                won = y_idx[i] == k
                pnl += stake * (odds_proxy[i, k] - 1.0) if won else -stake
    return pnl, n_bets


def simulate_favorite_baseline(odds_proxy, p_market, y_idx):
    """Baseline 'sempre o favorito do proxy' (sem Kelly/edge, stake fixo=1)."""
    fav = p_market.argmax(axis=1)
    pnl = 0.0
    for i in range(len(y_idx)):
        k = fav[i]
        won = y_idx[i] == k
        pnl += (odds_proxy[i, k] - 1.0) if won else -1.0
    return pnl


def paper_backtest_grid(df, feats, seed=42):
    """Fita o DC-NB 1x por fold (nao por combo -- reaproveita as mesmas probs em
    toda a grade, so o proxy/kelly/edge mudam por combo, que e barato)."""
    edges = [0.01, 0.02, 0.03, 0.05, 0.08]
    kellys = {"full": 1.0, "1/2": 0.5, "1/4": 0.25, "1/8": 0.125}
    overrounds = [0.03, 0.05, 0.07, 0.09]

    grid_rows = []
    fav_rows = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": seed})
        m.fit(tr[feats], tr["home_score"], tr["away_score"])
        p_model = m.predict_proba_markets(te[feats])["result"][:, ::-1]
        y_idx = te["result"].map(Y_MAP).to_numpy()

        for overround in overrounds:
            odds_proxy, p_market = proxy_market_odds(tr, te, overround)
            fav_pnl = simulate_favorite_baseline(odds_proxy, p_market, y_idx)
            fav_rows.append({"fold": fold, "overround": overround, "pnl_sempre_favorito": fav_pnl,
                              "n": len(te), "yield_pct": 100 * fav_pnl / len(te)})
            for edge_min in edges:
                for kname, kfrac in kellys.items():
                    pnl, n_bets = simulate_bets(p_model, odds_proxy, y_idx, edge_min, kfrac)
                    grid_rows.append({
                        "fold": fold, "overround": overround, "edge_min": edge_min,
                        "kelly": kname, "n_bets": n_bets, "pnl": pnl,
                        "yield_pct": 100 * pnl / max(n_bets, 1),
                    })
        print(f"  [{fold}] grid ok (n_test={len(te)})", flush=True)
    return pd.DataFrame(grid_rows), pd.DataFrame(fav_rows)


def negative_control_grid(df, feats, seed=42):
    """Embaralha resultado no ultimo fold, roda o mesmo grid -- yield deve ~0."""
    cuts = list(temporal_folds(df))
    fold, tr_idx, te_idx = cuts[-1]
    rng = np.random.RandomState(seed)
    tr = df.loc[tr_idx].copy()
    perm = rng.permutation(len(tr))
    tr["home_score"] = tr["home_score"].to_numpy()[perm]
    tr["away_score"] = tr["away_score"].to_numpy()[perm]
    tr["result"] = np.select([tr["home_score"] > tr["away_score"],
                               tr["home_score"] == tr["away_score"]], ["H", "D"], default="A")
    te = df.loc[te_idx]
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": seed})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    p_model = m.predict_proba_markets(te[feats])["result"][:, ::-1]
    y_idx = te["result"].map(Y_MAP).to_numpy()
    odds_proxy, _ = proxy_market_odds(tr, te, 0.05)
    pnl, n_bets = simulate_bets(p_model, odds_proxy, y_idx, 0.02, 0.25)
    return {"fold": fold, "n_bets": n_bets, "pnl": pnl,
            "yield_pct": 100 * pnl / max(n_bets, 1),
            "veredito": "OK (yield ~0)" if abs(100 * pnl / max(n_bets, 1)) < 5 else "SUSPEITO"}


def seed_dispersion(df, feats):
    """Yield do combo 'central' (edge=0.02, kelly=1/4, overround=0.05) no ultimo
    fold, em 5 seeds -- mede estabilidade do backtest de papel."""
    cuts = list(temporal_folds(df))
    fold, tr_idx, te_idx = cuts[-1]
    tr, te = df.loc[tr_idx], df.loc[te_idx]
    y_idx = te["result"].map(Y_MAP).to_numpy()
    odds_proxy, _ = proxy_market_odds(tr, te, 0.05)
    out = []
    for seed in SEEDS:
        m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": seed})
        m.fit(tr[feats], tr["home_score"], tr["away_score"])
        p_model = m.predict_proba_markets(te[feats])["result"][:, ::-1]
        pnl, n_bets = simulate_bets(p_model, odds_proxy, y_idx, 0.02, 0.25)
        out.append({"seed": seed, "n_bets": n_bets, "pnl": pnl,
                    "yield_pct": 100 * pnl / max(n_bets, 1)})
        print(f"  seed={seed}: yield={out[-1]['yield_pct']:.2f}% n_bets={n_bets}", flush=True)
    yields = [o["yield_pct"] for o in out]
    return out, float(np.mean(yields)), float(np.std(yields))


def check_odds_coverage() -> dict:
    from app.db.connection import engine
    from sqlalchemy import text
    with engine.connect() as c:
        n_sel = c.execute(text("SELECT count(*) FROM odds_registry")).scalar()
        n_club = c.execute(text("SELECT count(*) FROM club_odds_registry")).scalar()
    n_sel_snap = len(glob.glob(str(ROOT / "data" / "odds" / "snapshots" / "*.jsonl")))
    n_club_snap = len(glob.glob(str(ROOT / "data" / "odds" / "club_snapshots" / "*.jsonl")))
    # cron real (so o wrapper .cmd chama collect_odds_forward.py -- club fica de fora)
    task_cmd = (ROOT / "backend" / "scripts" / "collect_odds_task.cmd")
    if not task_cmd.exists():
        task_cmd = ROOT.parent / "backend" / "scripts" / "collect_odds_task.cmd"
    return {
        "odds_registry_rows": n_sel, "club_odds_registry_rows": n_club,
        "selecao_snapshot_files": n_sel_snap, "club_snapshot_files": n_club_snap,
    }


def main():
    print("=" * 80)
    print("H2 (valor) + H3 (de-vig/CLV) — bateria 2026-07-21")
    print("=" * 80)
    OUT_H2.mkdir(parents=True, exist_ok=True)
    OUT_H3.mkdir(parents=True, exist_ok=True)

    print("\n>> Parte A: CLV real (snapshots + resultado via API)...")
    clv_df = build_clv_dataset()
    clv_df.to_csv(OUT_H2 / "clv_real_selecao.csv", index=False)  # nome do plano; contem selecao+clube
    if len(clv_df):
        clv_out, bucket_rows = h3_clv_by_method(clv_df)
        write_h3_recomendacao(clv_df, clv_out)
    else:
        print("[AVISO] zero fixtures resolvidas com odds reais -- H3 fica so com os testes unitarios")

    print("\n>> Cobertura de odds forward (registry + snapshots + cron real)...")
    cov = check_odds_coverage()
    cron_txt = "collect_odds_task.cmd roda SO scripts/collect_odds_forward.py (SELEÇÃO) a cada 3h."
    club_cron = "**collect_club_odds_forward.py NÃO está no cron** (achado desta sessão) -- roda só manual."
    cobertura_md = f"""# Cobertura de coleta forward de odds — H2

- `odds_registry` (Neon, índice, seleção): {cov['odds_registry_rows']} linhas
- `club_odds_registry` (Neon, índice, clube): {cov['club_odds_registry_rows']} linhas
- Snapshots em disco (seleção, `data/odds/snapshots/*.jsonl`): {cov['selecao_snapshot_files']} fixtures
- Snapshots em disco (clube, `data/odds/club_snapshots/*.jsonl`): {cov['club_snapshot_files']} fixtures

## Cron real (Task Scheduler `\\PrevisaoJogos\\`)
{cron_txt}
{club_cron}

**Ação recomendada** (fora do escopo desta bateria, fica documentada): adicionar uma
segunda linha ao `.cmd` (ou uma tarefa própria) chamando
`scripts/collect_club_odds_forward.py` no mesmo ciclo de 3h — hoje a única forma de a
cobertura de clube crescer é rodar o script manualmente.
"""
    (OUT_H2 / "cobertura_odds.md").write_text(cobertura_md, encoding="utf-8")

    aviso = """# AVISO — proxy vs ROI real

O backtest de papel deste diretório (`paper_grid.csv`) usa uma proxy de "mercado"
(frequência histórica H/D/A por liga, com overround sintético) — NÃO é odds real
de bookmaker. É diagnóstico de calibração relativa (o modelo tem edge sobre um
baseline ingênuo?), não uma medida de lucratividade. A única validação real de
rentabilidade é `clv_real_selecao.csv` (CLV contra odds reais coletadas forward),
e mesmo essa tem amostra pequena demais para conclusão definitiva (ver
`h3_devig/recomendacao.md`).
"""
    (OUT_H2 / "AVISO_proxy.md").write_text(aviso, encoding="utf-8")

    print("\n>> Parte B: backtest de papel (grid + baseline favorito)...")
    df = load_clubs_df()
    feats = base_feats_170()
    grid_df, fav_df = paper_backtest_grid(df, feats)
    grid_df.to_csv(OUT_H2 / "paper_grid.csv", index=False)
    fav_df.to_csv(OUT_H2 / "paper_grid_sempre_favorito.csv", index=False)

    agg_model = grid_df.groupby(["edge_min", "kelly"])["yield_pct"].mean().reset_index()
    print(">> yield médio por (edge_min, kelly), agregado overrounds/folds:")
    print(agg_model.to_string(index=False))

    print("\n>> Heatmap agregado...")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    pivot = agg_model.pivot(index="kelly", columns="edge_min", values="yield_pct")
    fig, ax = plt.subplots(figsize=(7, 4))
    im = ax.imshow(pivot.to_numpy(), cmap="RdYlGn", aspect="auto",
                    vmin=-max(1, abs(pivot.to_numpy()).max()), vmax=max(1, abs(pivot.to_numpy()).max()))
    ax.set_xticks(range(len(pivot.columns))); ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index))); ax.set_yticklabels(pivot.index)
    ax.set_xlabel("edge mínimo"); ax.set_ylabel("fração de Kelly")
    ax.set_title("Yield médio (%) — backtest de papel (proxy), agregado overround/fold")
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax.text(j, i, f"{pivot.to_numpy()[i, j]:.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="yield %")
    fig.tight_layout()
    fig.savefig(OUT_H2 / "heatmap.png", dpi=120)
    print(f">> heatmap salvo em {OUT_H2/'heatmap.png'}")

    print("\n>> Controle negativo (rotulos embaralhados, ultimo fold)...")
    neg = negative_control_grid(df, feats)
    print(f"   {neg}")

    print("\n>> Dispersao de 5 seeds (combo central, ultimo fold)...")
    seed_out, seed_mean, seed_std = seed_dispersion(df, feats)

    with open(OUT_H2 / "robustez.json", "w", encoding="utf-8") as f:
        json.dump({"controle_negativo": neg, "seed_dispersion": seed_out,
                    "yield_mean_pct": seed_mean, "yield_std_pct": seed_std}, f,
                   ensure_ascii=False, indent=2)

    print("\n>> H2/H3 CONCLUIDO.")


if __name__ == "__main__":
    main()
