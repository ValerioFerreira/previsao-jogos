#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/tier2_player_cards_referee_test.py — Fator árbitro no prop de CARTÃO DE JOGADOR
========================================================================================
Terceira combinação (nunca isolada antes): já testamos (1) cartão de jogador SEM olhar
pro árbitro isoladamente e (2) rigor do árbitro no modelo de cartões por EQUIPE (agregado).
O que faltava medir de forma limpa era o efeito MARGINAL do `ref_strictness` dentro do
próprio modelo de jogador — porque, na prática, `scripts/test_player_cards.py` já inclui
`ref_strictness` no seu FEATS (está lá desde o commit original), então o AUC 0.634
"baseline" já reportado no doc-mestre JÁ EMBUTE o árbitro. Nunca foi isolado quanto do
0.634 vem do árbitro vs quanto vem só da forma do jogador.

Este script roda a MESMA validação temporal (mesmos cortes, mesmo classificador, mesmo
scope=clube, mesmos dados) duas vezes lado a lado:
  - "no_ref"   : FEATS sem ref_strictness (forma do jogador pura)
  - "with_ref" : FEATS + ref_strictness   (== exatamente o painel de test_player_cards.py)

`ref_strictness` é recomputado com a MESMA lógica de scripts/test_player_cards.py
(idêntica à usada em scripts/exp15_referee_cards.py para o modelo de equipe): média de
cartões (amarelo+vermelho) do árbitro por jogo, point-in-time (shift(1) + expanding,
min_periods=3, preenchido com a média global) — sem vazamento, pois só usa jogos que
esse árbitro apitou ESTRITAMENTE ANTES da partida corrente.

Não há um segundo sinal de árbitro "cartões médios totais" a adicionar: ref_strictness
JÁ É a média de cartões por jogo do árbitro — uma métrica de "média de cartões" separada
seria o mesmo número.

Gate: EXATAMENTE o mesmo de test_player_cards.py (AUC do modelo >= 0.68, ganho médio de
AUC sobre a taxa-base >= 0.02, consistente em quase todos os folds).

Uso: python scripts/tier2_player_cards_referee_test.py --scope clube
"""
import sys, warnings, argparse
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score

warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Reusa a lógica original ao invés de reinventar (mesma leitura de cache, mesmo cômputo
# de ref_strictness, mesma engenharia de features) — só NÃO modifica o arquivo original.
from scripts.test_player_cards import load_from_cache, referee_strictness, WINS

REPORT_DIR = ROOT / "data" / "reports" / "tier2_player_cards_referee"

FEATS_NO_REF = ["base_carded", "form_carded_5", "form_carded_10", "form_fouls_5",
                "minutes_base", "is_home", "pos_def", "pos_mid"]
FEATS_WITH_REF = FEATS_NO_REF + ["ref_strictness"]


def build_features(pg):
    """Idêntico a test_player_cards.build_features (replicado aqui só para poder manter
    as DUAS listas de features — sem o dropna fixo em FEATS globais do original)."""
    pg = pg[pg["minutes"] >= 1].copy()
    pg["carded"] = ((pg["yellow"] + pg["red"]) > 0).astype(int)
    gc = pg["carded"].mean()
    refmap, glob_ref = referee_strictness(pg)
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cc = g["carded"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri,
             "base_carded": (cc + 5 * gc) / (npri + 5),
             "minutes_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values,
             "form_fouls_5": g["fouls"].shift(1).rolling(5, min_periods=1).mean().values}
        for w in WINS:
            d[f"form_carded_{w}"] = g["carded"].shift(1).rolling(w, min_periods=1).mean().values
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns:
        pg[c] = F[c]
    pg["pos_def"] = (pg["pos"] == "D").astype(int)
    pg["pos_mid"] = (pg["pos"] == "M").astype(int)
    pg["ref_strictness"] = [refmap.get(k, glob_ref) for k in pg["key"]]
    pg["form_fouls_5"] = pg["form_fouls_5"].fillna(pg["fouls"].mean())
    return pg.dropna(subset=FEATS_WITH_REF + ["carded"]).reset_index(drop=True), gc


def ece_binary(y, p, nb=10):
    edges = np.linspace(0, 1, nb + 1)
    e = 0.0
    for b in range(nb):
        mk = (p >= edges[b]) & (p < edges[b + 1])
        if mk.mean() > 0:
            e += mk.mean() * abs(y[mk].mean() - p[mk].mean())
    return e


def temporal_validation(df):
    """Mesmos cortes/temporalidade de test_player_cards.temporal_validation, mas treina
    e avalia os DOIS paineis de features (no_ref / with_ref) no mesmo fold, mesmo split,
    mesmo classificador — comparação limpa e pareada."""
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4)
    res = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300:
            continue
        y_tr, y_te = tr["carded"], te["carded"].values
        pbase = te["base_carded"].clip(1e-4, 1 - 1e-4).values

        clf_a = HistGradientBoostingClassifier(max_iter=200, max_depth=3, learning_rate=0.05, random_state=42)
        clf_a.fit(tr[FEATS_NO_REF], y_tr)
        p_a = clf_a.predict_proba(te[FEATS_NO_REF])[:, 1]

        clf_b = HistGradientBoostingClassifier(max_iter=200, max_depth=3, learning_rate=0.05, random_state=42)
        clf_b.fit(tr[FEATS_WITH_REF], y_tr)
        p_b = clf_b.predict_proba(te[FEATS_WITH_REF])[:, 1]

        res.append(dict(
            fold=round(c, 2), n=len(te),
            auc_taxabase=roc_auc_score(y_te, pbase),
            auc_no_ref=roc_auc_score(y_te, p_a),
            auc_with_ref=roc_auc_score(y_te, p_b),
            ll_taxabase=log_loss(y_te, pbase, labels=[0, 1]),
            ll_no_ref=log_loss(y_te, p_a, labels=[0, 1]),
            ll_with_ref=log_loss(y_te, p_b, labels=[0, 1]),
            ece_no_ref=ece_binary(y_te, p_a),
            ece_with_ref=ece_binary(y_te, p_b),
        ))
    return pd.DataFrame(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], default="clube")
    a = ap.parse_args()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Carregando cache (scope={a.scope})...", flush=True)
    pg = load_from_cache(a.scope)
    df, gc = build_features(pg)
    print(f"player-games: {len(df)} | levou cartao={df.carded.mean():.3f} | "
          f"jogadores={df.player_id.nunique()}", flush=True)

    R = temporal_validation(df)
    pd.set_option("display.width", 160)
    print("\n=== VALIDACAO TEMPORAL (taxa-base vs sem-arbitro vs com-arbitro) ===", flush=True)
    print(R.round(4).to_string(index=False), flush=True)

    csv_path = REPORT_DIR / f"fold_comparison_{a.scope}.csv"
    R.to_csv(csv_path, index=False)

    auc_base = R.auc_taxabase.mean()
    auc_no = R.auc_no_ref.mean()
    auc_with = R.auc_with_ref.mean()
    d_ref = (R.auc_with_ref - R.auc_no_ref).mean()
    d_vs_base = (R.auc_with_ref - R.auc_taxabase).mean()
    win_ref = int((R.auc_with_ref > R.auc_no_ref).sum())
    win_base = int((R.auc_with_ref > R.auc_taxabase).sum())
    n = len(R)
    ece_with = R.ece_with_ref.mean()

    print(f"\n  >> AUC taxa-base {auc_base:.4f} | sem-arbitro {auc_no:.4f} | "
          f"com-arbitro {auc_with:.4f}", flush=True)
    print(f"  >> delta arbitro (with_ref - no_ref): {d_ref:+.4f} (melhora em {win_ref}/{n} folds)", flush=True)
    print(f"  >> delta vs taxa-base (with_ref): {d_vs_base:+.4f} (melhora em {win_base}/{n} folds)", flush=True)
    print(f"  >> ECE com-arbitro: {ece_with*100:.2f}%", flush=True)

    # MESMO gate de test_player_cards.py, aplicado ao painel COM arbitro (candidato final)
    ok = auc_with >= 0.68 and d_vs_base >= 0.02 and win_base >= n - 1
    veredito = "PROMOVER" if ok else "NAO PROMOVER (abaixo do padrao)"
    print(f"  >> VEREDITO (gate identico ao test_player_cards.py, threshold 0.68): {veredito}", flush=True)

    md = f"""# Veredito — Fator árbitro no prop de cartão de JOGADOR (scope={a.scope})

## Contexto
- Combinação #1 já testada (`scripts/test_player_cards.py`): cartão de jogador sem olhar
  isoladamente pro árbitro (embora o script ORIGINAL já incluísse `ref_strictness` no seu
  próprio FEATS) -> AUC reportado 0.634 (clube).
- Combinação #2 já testada (`scripts/exp15_referee_cards.py`): `ref_strictness` no modelo
  de cartões por EQUIPE (agregado) -> REPROVADO (3/7 folds, dNLL +0.007).
- Esta é a combinação #3: isola o efeito MARGINAL de `ref_strictness` dentro do próprio
  modelo de JOGADOR, comparando painel sem-arbitro vs com-arbitro na MESMA validação
  temporal (mesmos cortes, mesmo classificador, mesmo scope=clube).

## Cômputo do `ref_strictness` (reaproveitado, não reinventado)
Média de cartões (amarelo+vermelho) do árbitro por jogo, point-in-time:
`shift(1).expanding(min_periods=3).mean()` agrupado por árbitro, preenchido com a média
global quando não há histórico suficiente — sem vazamento (só jogos estritamente
anteriores). Idêntico ao usado em `test_player_cards.py::referee_strictness` e
equivalente em espírito ao `ref_strictness` de `exp15_referee_cards.py` (agregado por
partida, não por jogador).

## Resultado (folds temporais, scope={a.scope})
- AUC taxa-base: {auc_base:.4f}
- AUC sem árbitro (forma pura do jogador): {auc_no:.4f}
- AUC com árbitro (painel completo, = exatamente o FEATS de test_player_cards.py): {auc_with:.4f}
- Delta do árbitro (with_ref - no_ref): {d_ref:+.4f} (melhora em {win_ref}/{n} folds)
- Delta vs taxa-base (with_ref): {d_vs_base:+.4f} (melhora em {win_base}/{n} folds)
- ECE (com árbitro): {ece_with*100:.2f}%

Ver `fold_comparison_{a.scope}.csv` para os números por fold.

## Threshold (idêntico ao já usado para este prop)
Precisa: AUC do modelo candidato >= 0.68 E ganho médio sobre taxa-base >= 0.02 E
consistente em quase todos os folds ({n-1}/{n} ou mais).

## Veredito
**{veredito}**

AUC final ({auc_with:.4f}) {'atinge' if ok else 'fica abaixo de'} o piso de 0.68 já usado
para este prop. O ganho marginal do árbitro sobre a forma pura do jogador foi de
{d_ref:+.4f} AUC ({win_ref}/{n} folds em que with_ref > no_ref). {
"Isso é suficiente para cruzar o piso do site, então a combinação passa no gate mesmo com o "
"cartão de jogador sendo majoritariamente idiossincrático — o árbitro fecha a diferença."
if ok else
"Mesmo com uma amostra de clube ordens de magnitude maior que a de seleção (evidência a favor "
"de que o rigor do árbitro carrega algum sinal real e mensurável sobre o piso de probabilidade "
"da partida), o cartão de jogador continua dominado pela idiossincrasia individual/aleatoriedade "
"de jogo a jogo. Não há arredondamento para cima: um ganho marginal não é \"quase lá\" — é "
"REPROVADO pelo mesmo padrão do site, exatamente como as duas combinações testadas antes."
}

Não existe um segundo sinal de "cartões médios do árbitro" distinto de `ref_strictness` a
adicionar — a própria definição de `ref_strictness` já É a média (expanding) de cartões por
jogo do árbitro; qualquer variante seria redundante com o que já está no painel `with_ref`.
"""
    (REPORT_DIR / "veredito.md").write_text(md, encoding="utf-8")
    print(f"\nRelatorio salvo em {REPORT_DIR}", flush=True)


if __name__ == "__main__":
    main()
