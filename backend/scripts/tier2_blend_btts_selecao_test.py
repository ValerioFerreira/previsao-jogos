#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tier2_blend_btts_selecao_test.py
=========================================
`blend_btts` (blend DC-NB + HistGradientBoostingClassifier no mercado BTTS) foi testado
DUAS VEZES no dataset de CLUBE (`scripts/clubs_revisit_hypotheses.py::h_blend_btts`):
  - 1ª tentativa (13 ligas):  4/5 folds melhoram, delta abaixo do limiar de promoção.
  - 2ª tentativa (60 ligas, DOCUMENTACAO_CENTRAL.md §17.1): 5/5 folds melhoram, mas
    delta médio de log-loss = -0.0005, ainda abaixo do limiar -0.001 -> "misto".

NUNCA foi testado no dataset de SELEÇÃO. Este script replica EXATAMENTE a mesma
construção (mesma fórmula de blend 0.5/0.5, mesmas features = base_feats de produção,
mesmo protocolo `research_clubs.protocol.temporal_folds` de 5 folds temporais expanding)
sobre `international_features_enriched_apifootball.csv`, com o DC-NB de produção
(`DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, max_goals=12,
random_state=42)`) como baseline.

Não altera model_artifacts/, predictor.py nem nenhum código de produção. Script isolado,
não modifica o script original de clube.

Saída: data/reports/tier2_blend_btts_selecao/{folds.csv, negative_control.csv, veredito.md}
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import temporal_folds, ece_binary

CSV = ROOT / "international_features_enriched_apifootball.csv"
META = ROOT / "model_artifacts" / "meta.json"
OUT_DIR = ROOT / "data" / "reports" / "tier2_blend_btts_selecao"

# Mesmo limiar de promoção usado no gate §6 / clube (clubs_revisit_hypotheses.py::_save_and_report)
PROMOTION_DELTA = -0.001
PROMOTION_MIN_WINS = 4


def load_df():
    df = pd.read_csv(CSV)
    df["date"] = pd.to_datetime(df["date"])
    # mesmo filtro de maturidade usado em load_df() de clubs_revisit_hypotheses.py
    df = df[(df["home_matches_played_before"] >= 5) & (df["away_matches_played_before"] >= 5)]
    return df.sort_values("date").reset_index(drop=True)


def bf():
    return json.load(open(META, encoding="utf-8"))["base_feats"]


def bernoulli_logloss(y_true, p, eps=1e-12):
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))


def run_blend_btts(df, feats):
    from sklearn.ensemble import HistGradientBoostingClassifier

    rows = []
    last_fold_state = None  # guarda dados do último fold p/ controle negativo
    for fold, tr_idx, te_idx in temporal_folds(df):
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        X_tr = tr[feats].fillna(tr[feats].median(numeric_only=True))
        X_te = te[feats].fillna(tr[feats].median(numeric_only=True))

        m = DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05,
                                   max_goals=12, random_state=42)
        m.fit(X_tr, tr["home_score"].to_numpy(), tr["away_score"].to_numpy())
        p_dc = m.predict_proba_markets(X_te)["btts"]

        y_tr = tr["btts"].to_numpy()
        y_te = te["btts"].to_numpy()
        hgb = HistGradientBoostingClassifier(max_iter=200, random_state=42)
        hgb.fit(X_tr, y_tr)
        p_hgb = hgb.predict_proba(X_te)[:, 1]

        p_blend = 0.5 * p_dc + 0.5 * p_hgb

        ll_dc = bernoulli_logloss(y_te, p_dc)
        ll_blend = bernoulli_logloss(y_te, p_blend)
        ece_dc = ece_binary(y_te, p_dc)
        ece_blend = ece_binary(y_te, p_blend)

        rows.append({
            "fold": fold, "n": len(te),
            "btts_rate_train": float(y_tr.mean()), "btts_rate_test": float(y_te.mean()),
            "ll_dc": ll_dc, "ll_blend": ll_blend, "delta_ll": ll_blend - ll_dc,
            "melhora": ll_blend < ll_dc,
            "ece_dc": ece_dc, "ece_blend": ece_blend,
        })
        print(f"  [blend_btts_selecao] {fold}: n={len(te)} DC={ll_dc:.4f} blend={ll_blend:.4f} "
              f"delta={ll_blend - ll_dc:+.4f} ece_dc={ece_dc:.4f} ece_blend={ece_blend:.4f}",
              flush=True)

        last_fold_state = dict(fold=fold, y_te=y_te, p_dc=p_dc, p_hgb=p_hgb,
                                ll_dc=ll_dc, btts_rate_train=float(y_tr.mean()))

    res = pd.DataFrame(rows)
    return res, last_fold_state


def negative_control(state, seed=42):
    """No último fold: embaralha as previsões do HGB entre os jogos (quebra qualquer
    correspondência real com o jogo), reconstrói o blend e confirma que o ganho aparente
    desaparece. Compara contra a taxa-base REAL de BTTS do treino (não 50/50 arbitrário)."""
    rng = np.random.default_rng(seed)
    y_te = state["y_te"]
    p_dc = state["p_dc"]
    p_hgb = state["p_hgb"]
    base_rate = state["btts_rate_train"]

    perm = rng.permutation(len(p_hgb))
    p_hgb_shuffled = p_hgb[perm]
    p_blend_shuffled = 0.5 * p_dc + 0.5 * p_hgb_shuffled

    ll_dc = state["ll_dc"]
    ll_blend_shuffled = bernoulli_logloss(y_te, p_blend_shuffled)
    ll_base_rate = bernoulli_logloss(y_te, np.full_like(y_te, base_rate, dtype=float))

    rows = [{
        "fold": state["fold"], "n": len(y_te),
        "ll_dc_real": ll_dc,
        "ll_blend_shuffled_hgb": ll_blend_shuffled,
        "ll_constant_base_rate": ll_base_rate,
        "base_rate_used": base_rate,
        "shuffled_beats_dc": bool(ll_blend_shuffled < ll_dc),
    }]
    return pd.DataFrame(rows)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_df()
    feats = bf()
    missing = [f for f in feats if f not in df.columns]
    if missing:
        raise SystemExit(f"base_feats ausentes no CSV de seleção: {missing}")

    print(f"dataset seleção: {len(df)} jogos ({df['date'].min().date()} .. {df['date'].max().date()})")
    print(f"taxa BTTS geral: {df['btts'].mean():.4f}")

    res, last_fold_state = run_blend_btts(df, feats)
    res.to_csv(OUT_DIR / "folds.csv", index=False)

    wins = int(res["melhora"].sum())
    nfolds = len(res)
    delta_mean = float(res["delta_ll"].mean())
    ece_dc_mean = float(res["ece_dc"].mean())
    ece_blend_mean = float(res["ece_blend"].mean())
    ece_not_worse = ece_blend_mean <= ece_dc_mean + 1e-6

    if wins >= PROMOTION_MIN_WINS and delta_mean < PROMOTION_DELTA and ece_not_worse:
        veredito = "PASSA (candidato à promoção)"
    elif wins >= 2:
        veredito = "MISTO"
    else:
        veredito = "REPROVADO"

    print(f"\n[blend_btts_selecao] {wins}/{nfolds} folds melhoram | delta médio {delta_mean:+.4f} "
          f"| ECE DC {ece_dc_mean:.4f} -> blend {ece_blend_mean:.4f} -> {veredito}\n")

    neg = negative_control(last_fold_state)
    neg.to_csv(OUT_DIR / "negative_control.csv", index=False)
    print("[controle negativo - último fold]")
    print(neg.to_string(index=False))

    # ─── veredito.md ─────────────────────────────────────────────────────────
    clube_p1 = "4/5 folds melhoram (delta não promovido; abaixo do limiar de -0.001; não promovido)"
    clube_p2 = "5/5 folds melhoram, delta médio -0.0005 (MISTO — abaixo do limiar -0.001; não promovido)"

    lines = []
    lines.append("# Veredito — blend_btts (seleção)\n")
    lines.append(f"Dataset: `international_features_enriched_apifootball.csv`, "
                 f"filtro `matches_played_before>=5` em ambos os lados -> **{len(df)} jogos** "
                 f"({df['date'].min().date()} a {df['date'].max().date()}).\n")
    lines.append(f"Taxa real de BTTS (dataset filtrado): **{df['btts'].mean():.4f}**.\n")
    lines.append("Baseline: `DixonColesNBRegressor(n_estimators=100, max_depth=3, learning_rate=0.05, "
                 "max_goals=12, random_state=42)` (produção), 158 `base_feats` de "
                 "`model_artifacts/meta.json`. Candidato: blend `0.5*p_dc + 0.5*p_hgb` onde "
                 "`p_hgb` vem de `HistGradientBoostingClassifier(max_iter=200, random_state=42)` "
                 "treinado nas mesmas `base_feats` sobre o alvo binário `btts`. Protocolo: "
                 "`research_clubs.protocol.temporal_folds` (5 folds expanding, cortes "
                 "[0.50, 0.60, 0.70, 0.80, 0.85], mesmo usado em clube).\n")
    lines.append("## Resultado por fold\n")
    lines.append(res.to_markdown(index=False))
    lines.append("\n")
    lines.append(f"## Veredito final\n\n**{wins}/{nfolds} folds melhoram** | "
                 f"**delta médio de log-loss = {delta_mean:+.4f}** | "
                 f"ECE médio DC={ece_dc_mean:.4f} -> blend={ece_blend_mean:.4f} "
                 f"({'não piora' if ece_not_worse else 'PIORA'}).\n\n"
                 f"Limiar de promoção (mesmo do gate §6 / clube): >= {PROMOTION_MIN_WINS}/5 folds "
                 f"melhoram E delta < {PROMOTION_DELTA} E ECE não piora.\n\n"
                 f"**-> {veredito}**\n")
    lines.append("## Controle negativo (embaralhando p_hgb no último fold)\n")
    lines.append(neg.to_markdown(index=False))
    lines.append("\n")
    shuf_row = neg.iloc[0]
    lines.append(
        f"Com `p_hgb` embaralhado entre os jogos do último fold, o blend "
        f"({'ainda bate' if shuf_row['shuffled_beats_dc'] else 'NÃO bate'} o DC-NB: "
        f"log-loss shuffled={shuf_row['ll_blend_shuffled_hgb']:.4f} vs "
        f"DC real={shuf_row['ll_dc_real']:.4f}). Baseline de taxa-base real de treino "
        f"(**{shuf_row['base_rate_used']:.4f}**, não 50/50 arbitrário) tem log-loss "
        f"constante={shuf_row['ll_constant_base_rate']:.4f} — usado como piso de sanidade. "
        f"{'Confirma que o ganho aparente do blend depende de correspondência real jogo-a-jogo (controle passa).' if not shuf_row['shuffled_beats_dc'] else 'ATENÇÃO: controle negativo NÃO neutralizou o ganho — investigar vazamento/leakage antes de confiar no resultado acima.'}\n")

    lines.append("## Comparação com o histórico de clube\n\n")
    lines.append(f"- 1ª tentativa (clube, 13 ligas): {clube_p1}\n")
    lines.append(f"- 2ª tentativa (clube, 60 ligas, §17.1): {clube_p2}\n")
    lines.append(f"- Seleção (este teste, {len(df)} jogos, ~{len(df)/183530*100:.0f}% do tamanho do "
                 f"dataset de clube da 2ª tentativa): {wins}/{nfolds} folds melhoram, "
                 f"delta médio {delta_mean:+.4f} -> **{veredito}**.\n")

    (OUT_DIR / "veredito.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nRelatório salvo em {OUT_DIR}")


if __name__ == "__main__":
    main()
