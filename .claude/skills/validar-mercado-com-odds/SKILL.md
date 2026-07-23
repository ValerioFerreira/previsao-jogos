---
name: validar-mercado-com-odds
description: >-
  Valida e recalibra um mercado do modelo de previsão de futebol (ApostaInfo)
  contra ODDS REAIS de mercado. Use quando chegarem odds de teste de um mercado
  (BTTS, escanteios O/U, cartões O/U, handicap, etc.) e for preciso medir se o
  modelo identifica a odd justa (viés/precisão), decidir promoção sob gate, e
  gerar a correção de viés (bias_correction.joblib) que entra na produção.
  Dispara em: "validar mercado com odds", "recalibrar modelo com odds reais",
  "calibrar odd justa de <mercado>", "medir viés/precisão vs mercado".
---

# Validar e calibrar um mercado com odds reais

Metodologia consolidada (sessão 2026-07-23) para levar um mercado do modelo ao mesmo
padrão dos 3 já validados (1x2, Over/Under 2,5, handicap asiático): **o modelo estima a
probabilidade real → a odd justa é 1/p → medimos o erro do modelo contra a odd justa do
mercado (de-vigada) → corrigimos → a odd justa REAL entra na produção**. O ativo é ajudar
o usuário a achar odd melhor entre casas (line-shopping), NÃO prometer lucro.

## Pré-requisitos (dados)
1. **Prob do modelo** por saída do mercado (do `prediction_json` / `predictor.predict`).
2. **Odds reais** do mercado por jogo, de-vigáveis. Fontes (ver `data/reports/odds_sources.md`):
   API-Football `/odds` (BET_MAP em `scripts/fetch_odds.py`: btts=8, escanteios=45/57/58,
   cartões=80/82/83; retenção só ~7 dias → coleta forward acumula, ver `collect_odds_backfill.py`),
   football-data.co.uk (1x2/gols/handicap), Footiqo (BTTS), The Odds API (pago, corners/cards).
3. **Resultado real** do jogo pra rotular (do espelho local `club_raw_cache.sqlite` / `data/odds/results`).

## Passo a passo
1. **Montar pares (p_model, p_mercado)** por saída. De-vig das odds da casa com
   `scripts/devig_methods.py` (proporcional/power/**shin** — usar shin, é o recomendado). Para
   binário (over/under, sim/não, home/away de handicap), de-vig 2-vias:
   `p_fair = (1/odd_A) / (1/odd_A + 1/odd_B)`.
2. **Medir viés + precisão** (molde em `scripts/adhoc_metrics_fair_odds.py`):
   - viés = média(p_model − p_mercado) em pontos percentuais (todas as saídas). ~0 = modelo
     não-enviesado (esperado, bom).
   - precisão = MAE e RMSE de (p_model − p_mercado) em pp. É o "erro em cima da previsão".
   - break-even uplift = mediana de (1/p_mercado / odd_oferecida − 1) no lado recomendado = margem.
   - gap entre casas = mediana(Max/Avg − 1) no lado recomendado (prova do line-shopping).
   - Segmentar por liga; reportar N por segmento.
3. **Gate de promoção (PRÉ-REGISTRAR antes de olhar o resultado)** — ver `DOCUMENTACAO_CENTRAL.md §6`
   e o harness `research_clubs/corners_halftime/eval_halftime_smallN.py`
   (`grouped_stratified_kfold_repeated`, `leave_one_tournament_out`, `bootstrap_delta_ci`). Promover
   uma correção só se: (a) IC bootstrap 95% do ganho não cruza zero; (b) melhora em ≥60% dos
   folds/seeds; (c) leave-one-tournament-out não inverte. Se falhar, veredito honesto = "modelo já
   calibrado, correção = identidade" (é o caso dos 3 mercados atuais — viés já era ~0).
4. **Gerar a correção** (molde `scripts/build_bias_correction.py`): Platt logit-linear por mercado
   `p_corr = sigmoid(a·logit(p)+b)`, com **guarda anti-degeneração** (se slope sair de [0.5,1.5] ou
   logit quase constante → identidade a=1,b=0; senão colapsa tudo pra 0.5). Salvar a chave do novo
   mercado em `model_artifacts{,_clubes}/bias_correction.joblib`.
5. **Plugar na produção** — `app/services/odds.py::apply_bias` já lê `bias_correction[market_key]`
   e `fair_band` gera a faixa ±5% (95/100/105%). Basta adicionar o `market_key` do novo mercado no
   `enrich_with_odds` (binários) ou no `_mk`/mercados_derivados do `predictor.py` (derivados). O
   predictor carrega o joblib via `os.path.exists` (ausência = identidade).
6. **Registrar** o achado (números, veredito, N) em `backend/docs/ODD_JUSTA_E_CALIBRACAO.md` e, se
   for pesquisa de modelo, em `PESQUISA_CLUBES.md`.

## Guardrails de honestidade (inviolável)
- Viés ~0 é o resultado esperado e HONESTO — não force uma correção que "cria edge". Se o modelo já
  está calibrado, a correção é identidade e os números quase não mudam.
- De-vig é suposição de margem; usar o de-vig real por jogo, não um % fixo. `Max` é estatística de
  extremo (melhor de ~10 casas) — usar mediana no lado recomendado, nunca média de todas as saídas.
- Sem promessa de lucro. O valor é comparar casas (line-shopping), não bater o fluxo. Manter jogo
  responsável. Amostra pequena (<~300) → reportar como preliminar, não promover.

## Scripts de referência (já no repo)
- `scripts/adhoc_metrics_fair_odds.py` — viés/precisão/break-even/gap (1x2/OU/handicap). Molde.
- `scripts/build_bias_correction.py` — gera bias_correction.joblib (Platt + guarda).
- `scripts/adhoc_metrics_hitrates.py` / `adhoc_metrics_model_vs_naive.py` — taxas vs mercado / vs ingênuo.
- `scripts/devig_methods.py` — proporcional/power/shin.
- `scripts/collect_odds_backfill.py` — coleta a janela de odds da API-Football (7d passados + futuro).
- `research_clubs/corners_halftime/eval_halftime_smallN.py` — harness N-pequeno (k-fold/LOTO/bootstrap).
- `app/services/odds.py` (`apply_bias`, `fair_band`) + `predictor.py` (`bias_correction`) — produção.
