# Relatório 4 — Execução dos 6 próximos passos do handoff (sob gate temporal)

> Branch: **`claude-testing`**. `main` = produção. **Nada promovido.**
> Executados, exaustivamente e sob o **mesmo gate temporal** das baterias anteriores
> (CV expanding cuts 0.50→0.85, point-in-time, segmentado, métrica nativa por mercado),
> os 6 itens da seção "PRÓXIMOS PASSOS" do `HANDOFF_SESSAO_30062026.md`.
> Scripts em `backend/scripts/`, CSVs em `backend/data/reports/`.

## Estratégia de execução: um a um (sequencial), não em paralelo
Decisão deliberada. Numa **máquina única** com sklearn já usando todos os núcleos
(`n_jobs=-1`), rodar 6 scripts simultâneos **não acelera** — disputa de CPU, pressão de
memória (cada um carrega o CSV de 319 col / parquet) e monitoramento pior. O paralelismo
útil é **config-level dentro de cada experimento**. Mais importante: a **integridade do
gate** (comparar vs produção real, ortogonalização por fold, ler fold-a-fold E por
segmento) é serial por natureza — foi exatamente a atenção dispersa sobre validação que
produziu o falso-positivo do relatório 1. Subagents seriam contraproducentes (começam
frios e errariam a sutileza metodológica). Scripts resumíveis (checkpoint por mercado)
por causa do teardown de sessão (Armadilha nº4) — que de fato matou o Exp 4 uma vez.

---

## Veredito por experimento

| # | Experimento | Resultado | Promover? |
|---|---|---|---|
| 5 | xG de clube (contagem + resultado) | ganho só em finalizações, ~7× menor que o ruído entre folds | **Não** |
| 6 | Forma como blend de cobertura (resultado) | único sinal "âmbar": HGB melhora em 3 segmentos, mas decai com o tempo e só vs proxy | **Não (candidato a follow-up)** |
| 4/3 | Feature importance dos modelos de produção | entregue (interpretabilidade) | n/a |
| 3 | Cadeia de regressão (modelagem conjunta) | ΔLL ≈ 0 (\|média\| 0.002) | **Não** |
| 4 | Cópula bivariada mandante×visitante (total) | dependência pequena; sem ganho consistente | **Não** |
| 5 | Ataque×defesa→λ (estilo DC p/ contagem) | pior que GBR de produção em todos (ΔLL +0.03..+0.18) | **Não** |

---

### Item 5 — xG de clube (`xg_club_experiment.py`)
xG de clube (`form_xg_for/against`, já coletado; cobertura ~73%, diff ~58%) testado
**ALÉM** do `base_feats`, comparação justa (mesmas linhas com xG presente, N≈815 contagem
/ 1236 resultado).
- **Contagem:** melhora real só em **finalizações** (total ΔLL −0.019, mand/vis ~−0.013),
  mas o desvio entre folds é **~0.13** — ganho **~7× menor que o ruído**. Gols/escanteios/
  a-gol: sinais se cancelam, ECE frequentemente piora. Consistência por segmento 63% (≈moeda).
- **Resultado (H/D/A):** inconsistente (HGB −0.0098 em "todos" mas ECE pior; equilibrados
  pioram; o "ganho" de alta-cobertura é n=196 com LL-base 3.44 = overfit). **Não passa.**

### Item 6 — Forma como blend de cobertura (`forma_blend_experiment.py`)
Em vez de concatenar (reprovado no rel. 3), mistura de distribuições
`P = (1−w)·P_base + w·P_forma`, com `w = w0·cobertura` e `w0` calibrado **forward**.
- **Único resultado âmbar da sessão:** HGB melhora LogLoss nos **3 segmentos** (todos −0.0068,
  alta-cov −0.0430, equilibrados −0.0204) **sem piorar ECE**. Mas (a) LR fica neutro, (b) o
  ganho **decai por fold** (fold 0.50 −0.011 → fold 0.85 +0.001, ou seja some no regime mais
  atual), (c) medido contra **proxy HGB de base_feats, não contra o Dixon-Coles real**.
- **Veredito:** não promovível como está. **Follow-up honesto:** blendar a forma na saída do
  próprio DC de produção (não num proxy) e re-aplicar o gate. É o único fio que sobrou.

### Itens 3/4 — Feature importance dos modelos de PRODUÇÃO (`feature_importance_prod.py`)
Permutação sobre os **artefatos deployados** (não surrogates): ShotsNB, CornersNB,
ShotsOnTargetNB, CardsGP, DixonColesNB — holdout temporal (últimos 25%), métrica nativa
(log-loss), reproduzindo a ortogonalização de estilo e o cascade (OOF de finalizações +
interações) exatamente como no treino. Top features (ΔLL ao permutar):
- **Elo domina tudo:** `elo_home_winprob` é #1 em finalizações, a-gol, escanteios e no
  DC-resultado (ΔLL 0.20–0.47); no resultado todo o resto é <0.013.
- **Cascade finalizações→escanteios é real:** `pred_away_shots`/`pred_home_shots` são #2/#3
  em escanteios — e `pred_away_shots` é **#1 em cartões**.
- **PPDA de estilo (ortogonalizado)** aparece em todos os mercados (pressing é o sinal de
  estilo que sobrevive).
- **Cartões** é o mercado **menos guiado por elo** (top = pred-shots, recência de H2H,
  fadiga/jogos disputados, histórico de pênaltis) — o mais idiossincrático.

### Exp 3 — Cadeia de regressão / modelagem conjunta (`exp3_chain.py`)
Estende o cascade: posse→finalizações→a-gol/escanteios/cartões→gols, com upstream **OOF
no treino** (KFold) e modelo-cheio no teste (sem leakage), vs independente.
- **ΔLL ≈ 0** em tudo (\|média\| 0.0022; nenhum mercado além do ruído ~0.05; ECE-total de
  cartões −1.3pp é o único respiro, marginal). O `base_feats` já carrega o histórico rolante
  (`home_sb_shots_l5`…), então a predição encadeada agrega quase nada. **Não promover.**

### Exp 4 — Cópula bivariada mandante×visitante (`exp4_copula.py`)
Cópula gaussiana sobre as marginais NB, `rho` estimado point-in-time por fold (PIT), total
via Monte-Carlo (CDF em grade + searchsorted).
- **Dependência medida é pequena:** gols **+0.13/+0.16** e cartões **+0.23** (positiva — jogos
  faltosos/derby), escanteios **−0.17** e finalizações **−0.09** (negativa, confirma o
  β≈−0.04 anterior), a-gol ≈0.
- **Sem ganho no total:** ECE muda <0.7pp em todos. ⚠️ O LL de PMF-exata via MC ficou
  **dominado por ruído de discretização** (ΔLL +0.04 mesmo com rho≈−0.01 em a-gol), então o
  LL não resolve o efeito — mas a evidência (rho pequeno + ECE estável) é suficiente.
  Independência de produção para totais é defensável; o DC já modela a dependência de gols.

### Exp 5 — Ataque×defesa→λ estilo Dixon-Coles (`exp5_attack_defense.py`)
Forças por seleção (Poisson log-linear regularizado: `att_atacante + def_adversário +
mando`) + dispersão NB, vs GBR+features de produção.
- **Pior em todos:** ΔLL finalizações +0.177, a-gol +0.145, escanteios +0.110, cartões +0.032.
  Força-pura ignora elo/forma/estilo/H2H/descanso. O DC funciona em **gols** porque é
  DixonColesNB (usa features + histórico denso por seleção), não força-pura. **Não promover.**

---

## Conclusão
Confirma e estende o veredito das baterias 1–3: **a produção está robusta e bem calibrada;
o gate temporal honesto não promove nada destes 6 caminhos.** O elo satura o resultado; o
`base_feats` + cascade já captura o sinal de contagem; dependência bivariada é fraca e a
modelagem por força-pura é inferior. **Único fio vivo:** forma como **blend na saída do DC**
(item 6), a validar contra o modelo real — não contra proxy.

## Artefatos
Scripts: `xg_club_experiment.py`, `forma_blend_experiment.py`, `feature_importance_prod.py`,
`exp3_chain.py`, `exp4_copula.py`, `exp5_attack_defense.py` (todos em `backend/scripts/`,
resumíveis onde pesados). CSVs em `backend/data/reports/`: `xg_club_counts.csv`,
`xg_club_result.csv`, `forma_blend_result.csv`, `feature_importance_prod.csv` (1260 linhas),
`exp3_chain_results.csv`, `exp4_copula_results.csv`, `exp5_attack_defense_results.csv`.
