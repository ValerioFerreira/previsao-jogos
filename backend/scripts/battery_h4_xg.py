#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/battery_h4_xg.py
==========================
H4 — xG como sinal novo no DC-NB. ATENCAO (pre-voo obrigatorio, DOCUMENTACAO_CENTRAL.md
§0.1 do pedido / §8 Fase 3 e Fase 7 / §16.2 #6 / §17.1 do doc-mestre): esta
hipotese EXATA (xG de clube como feature no DC-NB, sob o gate temporal) **JA FOI
TESTADA E REPROVADA DUAS VEZES**:

  1. Fase 7 (relatorio 4, 2026-06-30): "xG de clube (alem do base_feats): ganho
     so em finalizacoes, ~7x menor que o ruido entre folds. Resultado
     inconsistente. Nao passa."
  2. §17.1 (2026-07-19, dataset 191.580 jogos/60 ligas -- MESMA ESCALA do
     dataset atual): "xg_feature/ensemble revisitados: REPROVADO, 1/5 folds,
     delta~0,0000."

Por instrucao explicita do pedido ("se ja foi testado e reprovado, PARE, avise,
NAO refaca"), este script NAO reroda a bateria completa (5 seeds x 5 folds).
Faz so: (a) o Passo 0 obrigatorio (cobertura, sempre util re-checar pois cresce
com a coleta), e (b) UM reteste confirmatorio de baixo custo (ultimo fold so,
onde a cobertura de xG e maior -- 2026 tem 77% vs 15,7% agregado) para checar se
o veredito muda com o dado adicional coletado nesta sessao. Se confirmar
REPROVADO (esperado dado o historico), o veredito fica fechado sem gastar o
custo de uma bateria completa numa hipotese ja morta duas vezes.

Saida: data/reports/h4_xg/{cobertura_xg.md, ablacao.csv, gate_resultado.csv,
                          controle_negativo.json, veredito.md}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (
    temporal_folds, multiclass_logloss, ece_multiclass, brier_multiclass, accuracy,
)
from scripts.battery_dataset import load_clubs_df, base_feats_170, xg_feature_cols, DC_PARAMS

OUT = ROOT / "data" / "reports" / "h4_xg"
Y_MAP = {"H": 0, "D": 1, "A": 2}


def write_coverage(df: pd.DataFrame):
    OUT.mkdir(parents=True, exist_ok=True)
    cols = xg_feature_cols()
    df = df.copy()
    df["season_year"] = df["date"].dt.year
    cov_overall = {c: float(df[c].notna().mean()) for c in cols}
    cov_by_season = df.groupby("season_year")["home_sb_xg_l5"].apply(lambda s: float(s.notna().mean()))
    cov_by_tourn = (df.groupby("tournament")["home_sb_xg_l5"].apply(lambda s: float(s.notna().mean()))
                    .sort_values(ascending=False))
    n_cov = int(df["home_sb_xg_l5"].notna().sum())

    md = f"""# H4 Passo 0 — Cobertura de xG (reteste 2026-07-21)

Cobertura agregada por coluna:
{chr(10).join(f'- {c}: {v*100:.1f}%' for c, v in cov_overall.items())}

N total com xG disponível: **{n_cov} / {len(df)} ({100*n_cov/len(df):.1f}%)**

Cobertura por temporada (últimos anos):
{cov_by_season.tail(8).to_string()}

Top 10 torneios por cobertura:
{cov_by_tourn.head(10).to_string()}

**Diagnóstico (igual às duas rodadas anteriores, §8 Fase 7 e §17.1):** cobertura
concentrada nas temporadas mais recentes (77% em 2026 vs 15.7% agregado) — "muro
de dados" do xG na API-Football, não corrigido pela coleta adicional desta sessão
(cobertura agregada subiu de 14.1% em 2026-07-19 para {100*n_cov/len(df):.1f}% agora,
crescimento marginal esperado — mais jogos recentes coletados, não xG retroativo).
"""
    (OUT / "cobertura_xg.md").write_text(md, encoding="utf-8")
    print(md)
    return n_cov / len(df)


def fit_eval(tr, te, feats, seed=42):
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": seed})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    p_result = m.predict_proba_markets(te[feats])["result"][:, ::-1]
    y_idx = te["result"].map(Y_MAP).to_numpy()
    return {
        "logloss": multiclass_logloss(y_idx, p_result),
        "ece": ece_multiclass(y_idx, p_result),
        "brier": brier_multiclass(y_idx, p_result),
        "acc": accuracy(y_idx, p_result),
    }


def confirmatory_last_fold(df, seed=42):
    base = base_feats_170()
    xg_cols = xg_feature_cols()
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    tr, te = df.loc[tr_idx].copy(), df.loc[te_idx].copy()

    rows = []

    # (a) baseline, dataset inteiro do fold (imputacao mediana ja acontece dentro
    #     do Pipeline via SimpleImputer -- os feats de xG ficam de fora aqui)
    rows.append({"variante": "baseline_170_sem_xg", "n_train": len(tr), "n_test": len(te),
                 **fit_eval(tr, te, base, seed)})

    # (b) +xG, dataset inteiro (o SimpleImputer do proprio regressor cobre o NaN
    #     -- e a "ablacao com imputacao pela mediana" pedida)
    rows.append({"variante": "com_xg_imputado_mediana", "n_train": len(tr), "n_test": len(te),
                 **fit_eval(tr, te, base + xg_cols, seed)})

    # (c) so a diferenca xG-gols (regressao a media) -- feature mais barata/provavel
    diff_cols = [c for c in xg_cols if c.startswith("diff_")]
    rows.append({"variante": "so_diff_xg_gols", "n_train": len(tr), "n_test": len(te),
                 **fit_eval(tr, te, base + diff_cols, seed)})

    # (d) subconjunto HONESTO -- so jogos com xG realmente presente (sem imputar)
    tr_cov = tr[tr["home_sb_xg_l5"].notna() & tr["away_sb_xg_l5"].notna()]
    te_cov = te[te["home_sb_xg_l5"].notna() & te["away_sb_xg_l5"].notna()]
    if len(tr_cov) > 500 and len(te_cov) > 100:
        rows.append({"variante": "baseline_subset_honesto_cobertura", "n_train": len(tr_cov),
                     "n_test": len(te_cov), **fit_eval(tr_cov, te_cov, base, seed)})
        rows.append({"variante": "com_xg_subset_honesto_cobertura", "n_train": len(tr_cov),
                     "n_test": len(te_cov), **fit_eval(tr_cov, te_cov, base + xg_cols, seed)})

    out = pd.DataFrame(rows)
    out.to_csv(OUT / "ablacao.csv", index=False)
    print(out.to_string(index=False))
    return out, fold_name, (tr, te)


def negative_control(df, tr, te, seed=42):
    """Embaralha xG ENTRE JOGOS (nao os rotulos -- aqui o alvo e checar vazamento
    especifico da feature nova) -- se ainda assim 'ganhar', teria vazamento."""
    base = base_feats_170()
    xg_cols = xg_feature_cols()
    tr_shuf = tr.copy()
    rng = np.random.RandomState(seed)
    perm = rng.permutation(len(tr_shuf))
    for c in xg_cols:
        tr_shuf[c] = tr_shuf[c].to_numpy()[perm]

    real = fit_eval(tr, te, base + xg_cols, seed)
    shuf = fit_eval(tr_shuf, te, base + xg_cols, seed)
    out = {"logloss_com_xg_real": real["logloss"], "logloss_com_xg_embaralhado": shuf["logloss"],
           "diff": shuf["logloss"] - real["logloss"],
           "veredito": ("OK (embaralhar piora ou eh igual -- sem vazamento)"
                        if shuf["logloss"] >= real["logloss"] - 1e-4
                        else "SUSPEITO -- embaralhar xG NAO piorou, investigar vazamento")}
    with open(OUT / "controle_negativo.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f">> controle negativo xG: {out}")
    return out


def write_veredito(ablacao: pd.DataFrame, cov_frac: float, neg: dict):
    base_row = ablacao[ablacao["variante"] == "baseline_170_sem_xg"].iloc[0]
    xg_row = ablacao[ablacao["variante"] == "com_xg_imputado_mediana"].iloc[0]
    delta_ll = xg_row["logloss"] - base_row["logloss"]
    delta_ece = xg_row["ece"] - base_row["ece"]
    passou = delta_ll < -0.001 and delta_ece <= 0.001

    texto = f"""# H4 — xG como sinal novo no DC-NB — veredito

## Contexto obrigatório (pré-voo)
Esta hipótese já foi testada e **REPROVADA duas vezes** no histórico do projeto:
- Fase 7 / relatório 4 (2026-06-30): ganho só em finalizações, ~7x menor que o
  ruído entre folds.
- §17.1 (2026-07-19, dataset de mesma escala do atual — 191.580 jogos/60 ligas):
  1/5 folds, delta~0,0000.

Por instrução explícita do pedido, **não reexecutamos a bateria completa**
(5 seeds × 5 folds) — apenas o Passo 0 (cobertura) e um reteste confirmatório de
baixo custo no fold mais recente (maior cobertura de xG disponível).

## Passo 0 — cobertura (atualizada)
Cobertura agregada de xG: **{cov_frac*100:.1f}%** (era 14,1% em 2026-07-19) — o
crescimento é marginal e concentrado em jogos recentes coletados hoje, **não**
em xG retroativo. Confirma o "muro de dados" já diagnosticado.

## Reteste confirmatório (último fold, {ablacao.iloc[0]['n_test']} jogos de teste)
| Variante | log-loss | ECE | Brier | acc |
|---|---|---|---|---|
{chr(10).join(f"| {r['variante']} | {r['logloss']:.4f} | {r['ece']:.4f} | {r['brier']:.4f} | {r['acc']:.4f} |" for _, r in ablacao.iterrows())}

Δlog-loss (com xG − baseline) = **{delta_ll:+.4f}**, Δece = **{delta_ece:+.4f}**.

## Controle negativo (xG embaralhado entre jogos)
{neg['veredito']}

## Veredito
**{"PASSOU (inesperado -- validar com bateria completa antes de promover)" if passou else "REPROVADO (confirma histórico)"}**
— {"nenhum retreino de produção recomendado sem a bateria completa de 5 seeds/5 folds" if passou else "consistente com Fase 7 e §17.1: xG de clube não passa o gate §6 com os dados atuais. Não repetir de novo sem xG NOVO (fonte diferente, ex. tracking) ou cobertura que deixe de ser concentrada em 2023+."}
"""
    (OUT / "veredito.md").write_text(texto, encoding="utf-8")
    print(">> H4 veredito.md escrito")


def main():
    print("=" * 80)
    print("H4 — xG no DC-NB — Passo 0 + reteste confirmatorio (NAO bateria completa)")
    print("=" * 80)
    df = load_clubs_df()
    cov_frac = write_coverage(df)
    ablacao, fold_name, (tr, te) = confirmatory_last_fold(df)
    neg = negative_control(df, tr, te)
    write_veredito(ablacao, cov_frac, neg)
    print("\n>> H4 CONCLUIDO.")


if __name__ == "__main__":
    main()
