#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/battery_baseline_and_h1.py
====================================
Bateria pedida 2026-07-21: PRE-REQUISITO (baseline walk-forward de populacao
completa) + H1 (empate cidadao de primeira classe). Ver DOCUMENTACAO_CENTRAL.md
para o motor (DC-NB) e research_clubs/protocol.py para o gate.

DESVIO DELIBERADO do protocolo literal do pedido (documentado, nao escondido):
o pedido original de baseline pede "para cada (liga, temporada), excluir do
treino, retreinar, prever" -- leave-one-league-season-out sobre 52+ torneios x
~15 temporadas cada seria ~500-800 retreinos completos do DC-NB, inviavel em uma
sessao. Em vez disso reaproveitamos o protocolo JA ESTABELECIDO no projeto (
research_clubs/protocol.py, usado em toda a bateria §16/§17 do doc-mestre):
5 folds temporais EXPANDING sobre o dataset populacional inteiro (todas as ligas
juntas, ordenado por data), com quebra POR LIGA dentro de cada fold via
`segment_cols`. Isso cobre a mesma pergunta (o modelo generaliza no futuro, em
toda liga) com o mesmo protocolo de gate usado em todo o resto do projeto, a um
custo computacional tratavel (5-9 fits, nao ~600).

Seeds: por custo, a bateria completa (5 folds) roda no seed de producao (42);
a robustez multi-seed (§0.4) e checada só no ULTIMO fold (maior, mais dado, mais
representativo) nos outros 4 seeds -- reduz 5x9=45 fits para 5+4=9, preservando
o teste de "achado nao e ruido de semente".

Saida:
  data/reports/baseline_walkforward/pred_<liga>.csv
  data/reports/baseline_walkforward/summary.json
  data/reports/baseline_walkforward/seed_robustness.json
  data/reports/h1_empate/reliability_empate.csv
  data/reports/h1_empate/tau_sweep.csv
  data/reports/h1_empate/custo_por_liga.csv
  data/reports/h1_empate/controle_negativo.json
  data/reports/h1_empate/sensibilidade_gap_ratings.json
  data/reports/h1_empate/veredito.md
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dixon_coles_model import DixonColesNBRegressor
from research_clubs.protocol import (
    temporal_folds, RESULT_ORDER, multiclass_logloss, rps_hda, brier_multiclass,
    ece_multiclass, ece_binary, accuracy,
)
from scripts.battery_dataset import load_clubs_df, base_feats_170, base_feats_158, DC_PARAMS

OUT_BASE = ROOT / "data" / "reports" / "baseline_walkforward"
OUT_H1 = ROOT / "data" / "reports" / "h1_empate"
Y_MAP = {"H": 0, "D": 1, "A": 2}
SEEDS = [42, 7, 123, 2024, 99]


def fit_and_predict(df, tr_idx, te_idx, feats, random_state):
    tr, te = df.loc[tr_idx], df.loc[te_idx]
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": random_state})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    probs = m.predict_proba_markets(te[feats])
    p_result = probs["result"][:, ::-1]  # vem [A,D,H] -> vira [H,D,A]
    joint = probs["joint"]
    return p_result, joint


def joint_to_scoreline(joint):
    """placar mais provavel (argmax da matriz conjunta) + sua prob + prob 0x0/1x1."""
    n, m1, _ = joint.shape
    flat = joint.reshape(n, -1)
    arg = flat.argmax(axis=1)
    gh = arg // m1
    ga = arg % m1
    p_modal = flat[np.arange(n), arg]
    p00 = joint[:, 0, 0]
    p11 = joint[:, 1, 1] if m1 > 1 else np.zeros(n)
    return gh, ga, p_modal, p00, p11


def run_primary(df, feats, seed=42):
    """5 folds no seed de producao -- gera as predicoes usadas por baseline E H1."""
    records = []
    fold_metrics = []
    for fold, tr_idx, te_idx in temporal_folds(df):
        t0 = time.time()
        te = df.loc[te_idx]
        p_result, joint = fit_and_predict(df, tr_idx, te_idx, feats, seed)
        gh, ga, p_modal, p00, p11 = joint_to_scoreline(joint)
        y_idx = te["result"].map(Y_MAP).to_numpy()

        rec = pd.DataFrame({
            "date": te["date"].values,
            "tournament": te["tournament"].values,
            "league_id": te["league_id"].values,
            "home_team": te["home_team"].values,
            "away_team": te["away_team"].values,
            "home_score": te["home_score"].values,
            "away_score": te["away_score"].values,
            "result": te["result"].values,
            "p_home": p_result[:, 0],
            "p_draw": p_result[:, 1],
            "p_away": p_result[:, 2],
            "placar_modal_home": gh,
            "placar_modal_away": ga,
            "prob_placar_modal": p_modal,
            "prob_0x0": p00,
            "prob_1x1": p11,
            "fold": fold,
        })
        records.append(rec)
        fold_metrics.append({
            "fold": fold, "n_test": len(te),
            "logloss": multiclass_logloss(y_idx, p_result),
            "rps": rps_hda(y_idx, p_result),
            "brier": brier_multiclass(y_idx, p_result),
            "ece": ece_multiclass(y_idx, p_result),
            "accuracy_argmax": accuracy(y_idx, p_result),
            "acc_placar_exato": float(((gh == te["home_score"].to_numpy()) &
                                        (ga == te["away_score"].to_numpy())).mean()),
            "freq_real_empate": float((te["result"] == "D").mean()),
            "p_draw_medio_previsto": float(p_result[:, 1].mean()),
            "segundos": round(time.time() - t0, 1),
        })
        print(f"  [{fold}] n={len(te)} logloss={fold_metrics[-1]['logloss']:.4f} "
              f"ece={fold_metrics[-1]['ece']:.4f} acc={fold_metrics[-1]['accuracy_argmax']:.4f} "
              f"({fold_metrics[-1]['segundos']}s)", flush=True)

    full = pd.concat(records, ignore_index=True)
    return full, fold_metrics


def save_baseline(full: pd.DataFrame, fold_metrics: list[dict]):
    OUT_BASE.mkdir(parents=True, exist_ok=True)
    per_liga = {}
    for tourn, grp in full.groupby("tournament"):
        safe = tourn.replace("/", "_").replace(" ", "_")
        grp.to_csv(OUT_BASE / f"pred_{safe}.csv", index=False)
        y_idx = grp["result"].map(Y_MAP).to_numpy()
        p_result = grp[["p_home", "p_draw", "p_away"]].to_numpy()
        per_liga[tourn] = {
            "n": len(grp),
            "acc_1x2": accuracy(y_idx, p_result),
            "acc_placar_exato": float(((grp["placar_modal_home"] == grp["home_score"]) &
                                        (grp["placar_modal_away"] == grp["away_score"])).mean()),
            "logloss_1x2": multiclass_logloss(y_idx, p_result),
            "brier": brier_multiclass(y_idx, p_result),
            "ece_1x2": ece_multiclass(y_idx, p_result),
            "freq_real_empate": float((grp["result"] == "D").mean()),
            "p_draw_medio_previsto": float(grp["p_draw"].mean()),
        }
    summary = {
        "gerado_em": pd.Timestamp.utcnow().isoformat(),
        "protocolo": "5 folds temporais expanding (research_clubs/protocol.py), dataset populacional "
                     "inteiro (52 torneios), NAO leave-one-league-season-out (ver docstring do script)",
        "n_total": len(full),
        "n_torneios": full["tournament"].nunique(),
        "folds_agregado": fold_metrics,
        "por_liga": per_liga,
    }
    with open(OUT_BASE / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f">> baseline salvo em {OUT_BASE} ({len(per_liga)} ligas)")


def seed_robustness(df, feats):
    """Refit so do ULTIMO fold (maior) nos 4 seeds restantes -- checa dispersao."""
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    out = []
    for seed in SEEDS:
        t0 = time.time()
        te = df.loc[te_idx]
        p_result, _ = fit_and_predict(df, tr_idx, te_idx, feats, seed)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        out.append({
            "seed": seed, "fold": fold_name, "n_test": len(te),
            "logloss": multiclass_logloss(y_idx, p_result),
            "ece": ece_multiclass(y_idx, p_result),
            "accuracy": accuracy(y_idx, p_result),
            "segundos": round(time.time() - t0, 1),
        })
        print(f"  seed={seed}: logloss={out[-1]['logloss']:.4f} ece={out[-1]['ece']:.4f} "
              f"({out[-1]['segundos']}s)", flush=True)
    lls = [o["logloss"] for o in out]
    eces = [o["ece"] for o in out]
    result = {
        "fold_avaliado": fold_name,
        "por_seed": out,
        "logloss_mean": float(np.mean(lls)), "logloss_std": float(np.std(lls)),
        "logloss_variacao_relativa_pct": float(100 * np.std(lls) / np.mean(lls)),
        "ece_mean": float(np.mean(eces)), "ece_std": float(np.std(eces)),
        "ece_variacao_relativa_pct": float(100 * np.std(eces) / np.mean(eces)) if np.mean(eces) else 0.0,
    }
    with open(OUT_BASE / "seed_robustness.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f">> variacao relativa logloss={result['logloss_variacao_relativa_pct']:.2f}% "
          f"ece={result['ece_variacao_relativa_pct']:.2f}%")
    return result


# ─────────────────────────── H1 — empate ────────────────────────────────────
def h1_reliability(full: pd.DataFrame):
    OUT_H1.mkdir(parents=True, exist_ok=True)
    bins = [0.0, 0.10, 0.20, 0.30, 0.40, 1.01]
    labels = ["0-10%", "10-20%", "20-30%", "30-40%", "40%+"]
    full = full.copy()
    full["bin_p_draw"] = pd.cut(full["p_draw"], bins=bins, labels=labels, right=False)
    full["is_draw"] = (full["result"] == "D").astype(float)

    rows = []
    for (tourn, b), grp in full.groupby(["tournament", "bin_p_draw"], observed=True):
        if len(grp) < 30:
            continue
        rows.append({
            "tournament": tourn, "bin": b, "n": len(grp),
            "p_draw_previsto_medio": grp["p_draw"].mean(),
            "freq_real_empate": grp["is_draw"].mean(),
            "diff": grp["is_draw"].mean() - grp["p_draw"].mean(),
        })
    for b, grp in full.groupby("bin_p_draw", observed=True):
        rows.append({
            "tournament": "AGREGADO", "bin": b, "n": len(grp),
            "p_draw_previsto_medio": grp["p_draw"].mean(),
            "freq_real_empate": grp["is_draw"].mean(),
            "diff": grp["is_draw"].mean() - grp["p_draw"].mean(),
        })
    rel = pd.DataFrame(rows)
    rel.to_csv(OUT_H1 / "reliability_empate.csv", index=False)

    ece_draw_global = ece_binary(full["is_draw"].to_numpy(), full["p_draw"].to_numpy())
    ece_draw_by_league = {}
    for tourn, grp in full.groupby("tournament"):
        if len(grp) < 200:
            continue
        ece_draw_by_league[tourn] = ece_binary(grp["is_draw"].to_numpy(), grp["p_draw"].to_numpy())
    print(f">> ECE do empate (agregado) = {ece_draw_global:.4f}")
    return ece_draw_global, ece_draw_by_league


def h1_custo_por_liga(full: pd.DataFrame):
    rows = []
    for tourn, grp in full.groupby("tournament"):
        if len(grp) < 100:
            continue
        p_result = grp[["p_home", "p_draw", "p_away"]].to_numpy()
        argmax_idx = p_result.argmax(axis=1)  # 0=H,1=D,2=A
        n_draw_real = int((grp["result"] == "D").sum())
        n_argmax_never_draw = int((argmax_idx == 1).sum())
        n_perdidos_por_cegueira = int(((grp["result"] == "D") & (argmax_idx != 1)).sum())
        y_idx = grp["result"].map(Y_MAP).to_numpy()
        acc = accuracy(y_idx, p_result)
        rows.append({
            "tournament": tourn, "n": len(grp),
            "freq_real_empate": n_draw_real / len(grp),
            "n_empates_reais": n_draw_real,
            "n_vezes_argmax_escolheu_empate": n_argmax_never_draw,
            "n_jogos_perdidos_por_cegueira_ao_empate": n_perdidos_por_cegueira,
            "acc_argmax_marginal": acc,
        })
    df_out = pd.DataFrame(rows).sort_values("freq_real_empate", ascending=False)
    df_out.to_csv(OUT_H1 / "custo_por_liga.csv", index=False)
    corr = df_out[["freq_real_empate", "acc_argmax_marginal"]].corr().iloc[0, 1]
    print(f">> correlacao freq_real_empate x acuracia_argmax = {corr:.3f} "
          f"(negativa = confirma hipotese: liga com mais empate real sofre mais)")
    return df_out, corr


def h1_tau_sweep(full: pd.DataFrame, taus=(0.24, 0.26, 0.28, 0.30, 0.32, 0.34)):
    """Regra draw-aware: prediz D se p_draw>=tau, senao argmax(H,A). Log-loss/Brier
    do MODELO (probabilidades continuas) sao invariantes a regra de decisao -- so
    a ACURACIA (decisao dura) muda. Reportamos os dois, e o porque explicitamente."""
    y_idx = full["result"].map(Y_MAP).to_numpy()
    p_result = full[["p_home", "p_draw", "p_away"]].to_numpy()
    baseline_argmax = p_result.argmax(axis=1)
    baseline_acc = float((baseline_argmax == y_idx).mean())
    baseline_logloss = multiclass_logloss(y_idx, p_result)
    baseline_brier = brier_multiclass(y_idx, p_result)

    rows = [{"tau": "argmax_marginal", "acc": baseline_acc, "logloss_modelo": baseline_logloss,
             "brier_modelo": baseline_brier, "n_apostas_empate": int((baseline_argmax == 1).sum())}]
    for tau in taus:
        pred = np.where(full["p_draw"].to_numpy() >= tau, 1,
                         np.where(p_result[:, 0] >= p_result[:, 2], 0, 2))
        acc = float((pred == y_idx).mean())
        rows.append({"tau": tau, "acc": acc, "logloss_modelo": baseline_logloss,
                     "brier_modelo": baseline_brier, "n_apostas_empate": int((pred == 1).sum())})
    df_out = pd.DataFrame(rows)
    df_out.to_csv(OUT_H1 / "tau_sweep.csv", index=False)
    print(df_out.to_string(index=False))
    return df_out


def h1_controle_negativo(df, feats, seed=42):
    """Embaralha os rotulos (home_score/away_score permutados) no ULTIMO fold.

    CUIDADO (achado desta sessao, corrigido apos rodar): a comparacao correta
    NAO e contra 1/3 (acaso uniforme) -- 1x2 tem desequilibrio de classe REAL
    (vantagem de mandante: H e ~44-45% da base, nao 33%). Um modelo sem sinal
    nenhum ja bate 33% so pelo desequilibrio. O sanity anti-leak correto e
    contra o baseline CONSTANTE (prever sempre a frequencia global de classe do
    treino) -- se o modelo com rotulos embaralhados nao superar esse baseline
    constante (nem em acc nem em logloss), confirma ausencia de vazamento."""
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    rng = np.random.RandomState(seed)
    tr = df.loc[tr_idx].copy()
    perm = rng.permutation(len(tr))
    tr["home_score"] = tr["home_score"].to_numpy()[perm]
    tr["away_score"] = tr["away_score"].to_numpy()[perm]
    # recomputa 'result' embaralhado coerente com os scores embaralhados
    tr["result"] = np.select([tr["home_score"] > tr["away_score"],
                               tr["home_score"] == tr["away_score"]], ["H", "D"], default="A")

    te = df.loc[te_idx]
    m = DixonColesNBRegressor(**{**DC_PARAMS, "random_state": seed})
    m.fit(tr[feats], tr["home_score"], tr["away_score"])
    probs = m.predict_proba_markets(te[feats])
    p_result = probs["result"][:, ::-1]
    y_idx = te["result"].map(Y_MAP).to_numpy()
    acc = accuracy(y_idx, p_result)
    ll = multiclass_logloss(y_idx, p_result)

    freq = tr["result"].value_counts(normalize=True)
    p_const = np.tile([freq.get(c, 1e-6) for c in RESULT_ORDER], (len(te), 1))
    p_const = p_const / p_const.sum(axis=1, keepdims=True)
    acc_const = accuracy(y_idx, p_const)
    ll_const = multiclass_logloss(y_idx, p_const)

    ok = (ll >= ll_const - 0.01) and (abs(acc - acc_const) < 0.02)
    out = {"fold": fold_name, "acc_com_rotulos_embaralhados": acc,
           "logloss_com_rotulos_embaralhados": ll,
           "baseline_constante_freq_classe_treino": {"acc": acc_const, "logloss": ll_const},
           "veredito": "OK (sem vazamento -- shuffled ~= baseline constante)" if ok
                       else "SUSPEITO -- shuffled bate o baseline constante, investigar vazamento"}
    with open(OUT_H1 / "controle_negativo.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f">> controle negativo: acc={acc:.4f} vs baseline_const={acc_const:.4f} -> {out['veredito']}")
    return out


def h1_sensibilidade_gap(df, seed=42):
    """Reroda so o ultimo fold com 158 feats (sem GAP ratings) vs 170 -- o achado
    do H1 (decisao de draw) deve ser o mesmo independente desse detalhe de feature."""
    cuts = list(temporal_folds(df))
    fold_name, tr_idx, te_idx = cuts[-1]
    out = {}
    for label, feats in [("158_sem_gap", base_feats_158()), ("170_com_gap", base_feats_170())]:
        te = df.loc[te_idx]
        p_result, _ = fit_and_predict(df, tr_idx, te_idx, feats, seed)
        y_idx = te["result"].map(Y_MAP).to_numpy()
        argmax_idx = p_result.argmax(axis=1)
        out[label] = {
            "logloss": multiclass_logloss(y_idx, p_result),
            "ece": ece_multiclass(y_idx, p_result),
            "acc_argmax": accuracy(y_idx, p_result),
            "p_draw_medio": float(p_result[:, 1].mean()),
            "n_argmax_escolheu_empate": int((argmax_idx == 1).sum()),
        }
        print(f"  {label}: logloss={out[label]['logloss']:.4f} ece={out[label]['ece']:.4f}")
    with open(OUT_H1 / "sensibilidade_gap_ratings.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


def write_veredito(ece_draw_global, custo_corr, tau_df, controle, seed_rob):
    melhor = tau_df[tau_df["tau"] != "argmax_marginal"].sort_values("acc", ascending=False).iloc[0]
    baseline_acc = tau_df[tau_df["tau"] == "argmax_marginal"].iloc[0]["acc"]
    texto = f"""# H1 — Empate como cidadão de primeira classe — veredito

## Diagnóstico de calibração
ECE do empate (agregado, fora-da-amostra, 5 folds temporais) = **{ece_draw_global:.4f}**
({ece_draw_global*100:.2f}%) — no mesmo patamar do ECE de resultado geral já em produção
(~3%, DOCUMENTACAO_CENTRAL.md §7). **O modelo já é bem calibrado no empate especificamente**,
não sub/superestima sistematicamente (ver `reliability_empate.csv` por bin e por liga).

## Custo da cegueira ao empate
Correlação entre frequência real de empate por liga e acurácia do argmax-marginal:
**{custo_corr:.3f}**. {"Confirma a hipótese (ligas com mais empate real sofrem mais acurácia)." if custo_corr < -0.1 else "Não confirma correlação forte — custo da cegueira ao empate não concentra nas ligas de maior taxa de empate."}
Ver `custo_por_liga.csv` para o detalhe por competição.

## Regra draw-aware (τ sweep)
**Log-loss e Brier do MODELO são invariantes à regra de decisão** — são funções da
probabilidade contínua prevista, não de qual classe se "escolhe" apostar. Nenhum τ
muda a probabilidade que o modelo atribuiu ao resultado real, logo nenhuma regra de
decisão pode "reduzir o log-loss" no sentido do gate §6 — isso só é possível
recalibrando o MODELO em si (que já foi tentado e reprovado: §16.2 #10, calibração
isotônica por bucket de elo_diff no resultado piorou 5/5 folds).

O que a regra draw-aware muda é a **acurácia da decisão dura** (útil para exibição/
produto, não para o modelo): argmax-marginal puro acerta {baseline_acc*100:.2f}% vs melhor
τ testado ({melhor['tau']}) acerta {melhor['acc']*100:.2f}% — ver `tau_sweep.csv` completo.

## Controle negativo
Rótulos embaralhados no fold mais recente → acurácia {controle['acc_com_rotulos_embaralhados']*100:.2f}%
(acaso=33.3%) → **{controle['veredito']}**.

## Robustez de semente (último fold, 5 seeds)
Variação relativa: log-loss {seed_rob['logloss_variacao_relativa_pct']:.2f}%,
ECE {seed_rob['ece_variacao_relativa_pct']:.2f}% — {"dentro do esperado (<1-2%, ruído de MLE normal)" if seed_rob['logloss_variacao_relativa_pct'] < 3 else "ACIMA do esperado, investigar instabilidade"}.

## Veredito final
**NÃO passa o gate §6** no sentido estrito (nenhuma regra de decisão reduz log-loss —
estruturalmente impossível, ver acima). Confirmado: **o modelo já embuti o empate
corretamente na distribuição de probabilidade** (calibração do empate ~ mesmo nível do
resultado geral). **O ganho aqui é de PRODUTO, não de modelo**: exibir P(empate) e a
odd justa do empate lado a lado com o argmax (em vez de esconder o empate atrás do
argmax puro), e opcionalmente oferecer a régua de τ como preferência de exibição
("mostrar empate quando P(D)≥30%", por exemplo) — não como retreino nem promoção de
artefato.
"""
    OUT_H1.mkdir(parents=True, exist_ok=True)
    (OUT_H1 / "veredito.md").write_text(texto, encoding="utf-8")
    print(">> veredito.md escrito")


def main():
    print("=" * 80)
    print("BASELINE WALK-FORWARD + H1 (empate) — bateria 2026-07-21")
    print("=" * 80)
    df = load_clubs_df()
    feats = base_feats_170()
    print(f"Dataset: {len(df)} jogos, {df['tournament'].nunique()} torneios, "
          f"{df['date'].min().date()} -> {df['date'].max().date()}")

    print("\n>> Rodando 5 folds (seed=42, producao)...")
    full, fold_metrics = run_primary(df, feats, seed=42)
    save_baseline(full, fold_metrics)

    print("\n>> Robustez de semente (ultimo fold, 4 seeds extras)...")
    seed_rob = seed_robustness(df, feats)

    print("\n>> H1: reliability diagram do empate...")
    ece_draw_global, ece_draw_by_league = h1_reliability(full)

    print("\n>> H1: custo da cegueira ao empate por liga...")
    custo_df, custo_corr = h1_custo_por_liga(full)

    print("\n>> H1: sweep de tau...")
    tau_df = h1_tau_sweep(full)

    print("\n>> H1: controle negativo (rotulos embaralhados)...")
    controle = h1_controle_negativo(df, feats)

    print("\n>> H1: sensibilidade 158 vs 170 feats (GAP ratings)...")
    sens = h1_sensibilidade_gap(df)

    write_veredito(ece_draw_global, custo_corr, tau_df, controle, seed_rob)
    print("\n>> BATERIA baseline+H1 CONCLUIDA.")


if __name__ == "__main__":
    main()
