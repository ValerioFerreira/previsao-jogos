# PLANO COMPLETO — Pesquisa de Modelos para Clubes (branch `clubs`)

> **Status: AGUARDANDO REVISÃO DO USUÁRIO.** A fase 1 (bateria de resultado) foi executada;
> os achados estão em `PESQUISA_CLUBES.md` §4. **Nada abaixo foi executado.** Este documento
> descreve TUDO o que seria feito para concluir a diretriz, fase a fase, com cada script,
> cada teste, custo estimado de máquina e critério de decisão. Aprovar/editar/cortar à vontade.

## O que já existe (executado antes desta pausa)

| Item | Artefato | Estado |
|---|---|---|
| Espelho local do bruto (54.072 jogos) | `data/club_raw_cache.sqlite` + `scripts/mirror_club_cache.py` | ✅ completo |
| Dataset de treino de clubes (54k × 346, 158/158 base_feats) | `data/built/club_features_enriched.parquet` + `scripts/build_clubs_dataset.py` | ✅ validado |
| Protocolo único (folds temporais + RPS/ECE/tail-ECE/cobertura) | `research_clubs/protocol.py` | ✅ testado |
| Ratings da literatura (pi/Berrar/GAP) | `research_clubs/ratings.py` | ✅ testado |
| DC clássico (xi-decay) + Poisson bivariado K&N | `research_clubs/stat_models.py` | ✅ testado |
| GBM wrappers (CatBoost/LGBM/XGB/ordered-logit) | `research_clubs/gbm_models.py` | ✅ testado |
| Bateria fase 1 — resultado H/D/A, 8 candidatos | `scripts/run_clubs_battery.py` → `data/reports/clubs_battery/` | ✅ executada (achados no doc-mestre) |

---

## FASE 2 — Linha A completa: mercados de contagem + calibração (clubes)

**Objetivo:** replicar TODA a arquitetura de produção sobre clubes (não só o resultado).

| # | Passo | Script (novo) | O que faz | Custo est. |
|---|---|---|---|---|
| 2.1 | Cascata de contagem | `scripts/clubs_train_counts.py` | Treina NB de finalizações (grid r×time-decay H∈{0,1,2,4}), NB a-gol, NB escanteios (grid r_H/r_A), GP cartões — mesma cascata de produção (pred_shots como feature downstream), sobre o subconjunto com box-score (36,9k jogos, 9× o de seleções). Walk-forward nos 5 folds do protocolo; PMF log-loss/MAE/cobertura80/tail-ECE | 1–2 h |
| 2.2 | Ortogonalização de estilo | idem 2.1 | Re-ajusta `style_ortho_weights` por fold (residualização vs Elo), como manda o gate §6.2 | incluso |
| 2.3 | Meio-tempo | `scripts/clubs_train_halves.py` | NB gols/cartões 1T/2T (clubes têm `score.halftime` em ~100% dos jogos) | 30 min |
| 2.4 | Calibração isotônica O/U | `scripts/clubs_build_ou_calibrators.py` | Walk-forward por mercado×lado (12 chaves como produção); promove só o que melhora BLL+ECE em ≥3/4 folds | 30 min |
| 2.5 | Hiperparâmetros do DC-NB | `scripts/clubs_tune_dc.py` | Grid GBM (n_estimators×depth×lr: 27 combos) + r_H/r_A/rho por MLE, sob os 5 folds. Clubes têm 5× dados → depth maior pode passar a valer (em seleções saturou em 3) | 3–6 h (20 núcleos) |
| **Gate da fase** | | | Relatório comparando cada mercado vs "mesmos hiperparâmetros de seleções" — responde à pergunta 1 da diretriz ("a arquitetura continua a melhor com mais dados?") | |

## FASE 3 — Linha A: transferência clubes → seleções

**Objetivo:** responder à pergunta 2 da diretriz ("o conhecimento de clubes melhora seleções?").

| # | Teste | Script | Método | Custo |
|---|---|---|---|---|
| 3.1 | Zero-shot | `scripts/clubs_transfer_selections.py` | Modelos treinados SÓ em clubes prevendo seleções (features idênticas por construção); compara log-loss/RPS/ECE vs produção nos mesmos folds temporais de seleções | 30 min |
| 3.2 | Pooled | idem | Treina em clubes+seleções juntos (com flag `is_national` e peso amostral variável w∈{0.25,0.5,1.0} para clubes) | 1–2 h |
| 3.3 | Fine-tuning | idem | Warm-start: hiperparâmetros/estrutura aprendidos em clubes, re-fit final só em seleções (GBM re-treinado; r/rho re-estimados) | 1 h |
| 3.4 | Só hiperparâmetros | idem | A config vencedora do tuning de clubes (2.5) re-treinada em seleções — teste mais limpo de "conhecimento transferido" | 30 min |
| **Gate da fase** | | | **Exceção de push**: se algum modo der ganho consistente (≥4/5 folds, sem piorar ECE, por segmento) → commit isolado na `main` + push, como manda a diretriz. Senão, documentar negativo | |

## FASE 4 — Linha A: revisita das hipóteses descartadas (base 9–13× maior)

Cada hipótese reprovada em seleções re-executada com o MESMO script conceitual, agora sobre
clubes (36,9k jogos com box-score vs 4,1k). Um script guarda-chuva resumível:
`scripts/clubs_revisit_hypotheses.py --only <nome>`.

| # | Hipótese (veredito em seleções) | Por que pode virar | Custo |
|---|---|---|---|
| 4.1 | Time-decay em gols/escanteios/cartões (só ajudou chutes) | clubes jogam 50+ jogos/ano → forma decai mais rápido; decay pode ganhar sinal | 30 min |
| 4.2 | Momentum/forma de equipe no resultado (reprovado 3×) | amostra 10×; em clubes forma é menos ruidosa (elenco estável semana a semana) | 30 min |
| 4.3 | Blend DC + HistGBM no BTTS (marginal 3/6) | mais dados estabilizam o blend | 30 min |
| 4.4 | Regressor λ/μ XGBoost/LGBM (nunca bateu sklearn GBM) | boosters potentes overfitavam 4k jogos; com 37k podem passar o sklearn | 2–4 h |
| 4.5 | Calibração post-hoc do RESULTADO (piorava) | DC pode descalibrar em clubes (empate 25% vs 28%) | 15 min |
| 4.6 | Árbitro (amostra rasa em seleções) | árbitros de liga têm 50–300 jogos cada na base; `referee` presente no raw | 1 h |
| 4.7 | Perfil Elo-condicionado (inconsistente por competição) | 13 competições com amostra grande p/ testar consistência de verdade | 1 h |
| 4.8 | xG como feature de λ/μ (muro de dados) | 10,2k jogos com xG (vs ~600) — o muro caiu; testar xG-rolling no DC e nas contagens | 1 h |
| 4.9 | GP vs NB por mercado (empate) | re-medir com PMFs mais povoadas | 30 min |
| **Gate** | | Cada uma sob o protocolo; registrar TUDO no diário §4 (positivos e negativos) | |

## FASE 5 — Linha B: engenharia de atributos própria de clubes

Novo módulo `research_clubs/club_features.py` + rebuild do parquet (v2):

| # | Grupo de features | Fonte | Nota |
|---|---|---|---|
| 5.1 | Congestão: jogos nos últimos 7/14/30 dias, dias desde último jogo em QUALQUER competição | fixtures | clubes jogam 2×/semana — não existe em seleções |
| 5.2 | Viagem: distância venue→venue anterior (geocode das ~800 cidades, cache local), altitude (Libertadores: La Paz/Quito/Bogotá) | `venue_city` | tabela estática de lat/lon/alt |
| 5.3 | Fase: `season_progress`, mata-mata ida/volta (agregado do confronto), "decisão" (final/semi) | `round` | ida/volta requer parear fixtures do mesmo confronto |
| 5.4 | Rotação/elenco: nº de mudanças no XI vs jogo anterior (lineups no raw), idade média do XI | `lineups`/`players` | parse adicional do raw (barato, espelho local) |
| 5.5 | xG estendido: xG-diff rolling, over/under-performance (gols−xG) l5/l10 (proxy de finalização/sorte) | box-score | literatura: regressão à média do (gols−xG) é sinal real |
| 5.6 | GAP ratings por estatística (chutes, escanteios, cartões) como features das contagens | ratings.py (já pronto) | plugar no dataset |
| 5.7 | Importância da partida: distância p/ zona (título/rebaixamento/vaga continental) via tabela corrente simulada | standings derivadas dos resultados | mais trabalhoso; opcional-alto-valor |
**Teste:** ablação por grupo sob o protocolo (cada grupo entra sozinho sobre o baseline vencedor
da fase 1; depois melhor combinação). Custo: 1 dia de máquina somando tudo.

## FASE 6 — Linha B: bateria avançada de modelos (hardware pleno)

| # | Candidato | Script | Detalhe | Custo est. |
|---|---|---|---|---|
| 6.1 | Sweep de hiperparâmetros dos vencedores da fase 1 | `scripts/clubs_sweep_winners.py` | Optuna/grid ~200 configs × 5 folds no(s) top-2 (CatBoost/LGBM), 20 núcleos | 4–12 h |
| 6.2 | Sweep dos ratings | idem | λ/γ do pi-rating (grid 8×5), Berrar (α,β,ω), xi do DC dinâmico (0→3 em 0,25) | 2–4 h |
| 6.3 | State-space Koopman-Lit | `research_clubs/state_space.py` | Intensidades att/def AR(1) por time, estimação por filtro (aprox. gaussiana/score-driven, sem MCMC), por liga | 1–2 dias de implementação + 4 h de máquina |
| 6.4 | GAP→contagens | `scripts/clubs_gap_counts.py` | GAP ratings de chutes/escanteios como λ de NB — compara com a cascata da produção | 2 h |
| 6.5 | Placar exato híbrido | `research_clubs/hybrid_score.py` | λ/μ do GBM vencedor + acoplamento DC/cópula re-estimado em clubes; compara matriz conjunta contra DC-NB | 3 h |
| 6.6 | Stacking/ensemble | `scripts/clubs_ensemble.py` | Meta-learner logístico sobre probs out-of-fold dos top-3 candidatos + odds (onde houver) | 2 h |
| 6.7 | (Opcional) Deep tabular | `scripts/clubs_deep_tabular.py` | TabNet/FT-Transformer (instalar torch CPU) — literatura diz que não bate GBM; só se 6.1–6.6 saturarem | 1 dia |
| **Gate** | | Ranking final sob o protocolo; vencedor = "melhor arquitetura para clubes" | |

## FASE 7 — Linha B → seleções

Repetir a fase 3 (zero-shot/pooled/fine-tune/hiperparâmetros) com as arquiteturas VENCEDORAS
da linha B. Mesma exceção de push se bater produção sob o gate §6. Script:
`scripts/clubs_b_transfer_selections.py`. Custo: 2–4 h.

## FASE 8 — Backtest de valor (ROI/EV) em clubes

- `scripts/clubs_value_backtest.py`: onde `odds_registry` tiver snapshot de clubes (coleta de
  odds é recente — cobertura pequena), computar ROI/EV/yield do vencedor vs odds de consenso;
  complementar com RPS vs odds implícitas (proxy de eficiência de mercado).
- Também vale rodar o backtest "de papel": Kelly fracionário simulado nos folds de teste.
- Custo: 2 h. **Este é o item §9.1 do doc-central (maior prioridade histórica do projeto).**

## FASE 9 — Consolidação e decisão

1. `PESQUISA_CLUBES.md` §4 (diário) completo com TODOS os números (positivos e negativos).
2. Relatório executivo: (a) melhor arquitetura p/ clubes; (b) resposta às 2 perguntas da
   diretriz; (c) o que (se algo) promover em seleções → aplicar exceção de push.
3. Artefatos finais de clubes em `model_artifacts_clubs/` (fora do caminho da produção).
4. Memória do agente atualizada; commits finais na `clubs`.

## Ordem de execução proposta e custo total

```
FASE 2 (1 dia) → FASE 3 (meio dia) → FASE 4 (1 dia) → FASE 5 (1 dia)
→ FASE 6 (2-3 dias, maior parte máquina) → FASE 7 (meio dia) → FASE 8-9 (1 dia)
≈ 6-8 dias corridos, sendo a maior parte tempo de máquina não-assistido
```

**Pontos de decisão para o usuário (marcar o que aprovar):**
- [ ] Executar fases 2–4 (Linha A completa) como descrito?
- [ ] Fase 5: incluir 5.7 (importância da partida — mais trabalhosa)?
- [ ] Fase 6: incluir 6.3 (state-space — maior esforço de implementação)? e 6.7 (deep tabular)?
- [ ] Fase 8: backtest de valor já nesta pesquisa ou depois?
- [ ] Alguma prioridade diferente na ordem?
