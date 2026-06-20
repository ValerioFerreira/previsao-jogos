# CONTEXTO — Análise de Importância de Features

> Documento autossuficiente para o Claude Code executar a análise de importância de
> features do projeto de previsão de jogos de seleções. Leia tudo antes de codar.

---

## 1. Objetivo

Descobrir, de forma rigorosa e conclusiva, **quais variáveis mais influenciam** cada
alvo de previsão do modelo. O resultado tem dois usos:
1. Entender o que de fato determina os resultados (objetivo analítico do projeto).
2. Alimentar uma decisão de UX futura: definir as ~10 variáveis pré-jogo de maior
   impacto que o usuário poderá editar na interface.

Esta é uma análise OFFLINE sobre dados e modelos JÁ EXISTENTES. Não coleta dados novos
(não usa a API), não re-treina os modelos de produção, não altera a interface.

---

## 2. Estado atual do projeto (contexto)

- Base de dados consolidada: ~9.976 jogos de seleções (2016+), dos quais **4.102 têm
  estatísticas avançadas completas** (chutes, chutes ao gol, escanteios, cartões).
- Dataset de features: `international_features_enriched_apifootball.csv` (raiz do
  projeto) — contém as features pré-jogo (Elo, forma móvel l3/l5/l10, h2h, descanso,
  contexto de torneio) e as médias móveis das estatísticas avançadas, mais a flag
  `has_advanced_stats`.
- Modelos treinados (desenvolvimento): `api/model_artifacts_apifootball/`
  (RandomForest para classificação; GradientBoosting quantílico q10/q50/q90 para
  regressão).
- Pipeline de features: lógica em `build_final_dataset.py`; treino em
  `train_and_save_apifootball.py`.
- Princípio inegociável: features são todas PRÉ-JOGO (sem data leakage). Estatísticas
  da própria partida nunca são preditor — só viram features via médias móveis dos
  jogos anteriores.

---

## 3. Alvos a analisar

Para cada alvo, identificar as features mais influentes:
1. **Resultado** (vencedor: vitória mandante / empate / vitória visitante) — classificação
2. **Total de gols** — regressão
3. **Escanteios de cada time** (mandante e visitante) — regressão
4. **Chutes e chutes ao gol** — regressão
5. **Cartões** — regressão

### Split por tempo (1º / 2º tempo) — LIMITAÇÃO IMPORTANTE
- Viável APENAS para **gols e cartões** (têm minuto registrado nos eventos da API).
- NÃO é viável para escanteios e chutes (a API só fornece o total do jogo, sem
  timestamp por evento). Para esses, a análise é sobre o total da partida.
- Onde o split for viável (gols, cartões), gerar a análise de importância separada
  para 1º e 2º tempo, além do total. Se os alvos por tempo ainda não existem como
  colunas, derivá-los dos eventos (gols por `score.halftime`; cartões pelos eventos
  com minuto <= 45 vs > 45).

---

## 4. Métodos a usar (combinação completa)

Aplicar e cruzar múltiplos métodos — nenhum isolado é suficiente:

1. **SHAP values** (principal): ranking global de importância + direção do efeito +
   interações. Usar TreeExplainer (compatível com os modelos de árvore). Gerar:
   - ranking de importância média absoluta por feature;
   - summary plot (efeito e direção);
   - dependence plots para as features de topo.
2. **Importância por permutação** (validação): mede a queda de performance ao
   embaralhar cada feature. Calcular sobre conjunto de teste/validação, não no treino.
   Usar scoring apropriado (neg_log_loss para classificação; neg_MAE/neg_RMSE para
   regressão).
3. **Importância nativa das árvores** (Gini/ganho): rápida, como sanity check. Anotar
   o viés conhecido (superestima features contínuas/alta cardinalidade).
4. **Informação mútua**: captura relação não-linear feature-alvo (triagem). Uma
   variável por vez.
5. **Correlação** (Pearson/Spearman): só como baseline visual de partida.

Para cada alvo, produzir um **ranking consolidado** que cruze SHAP + permutação (os
dois métodos mais confiáveis). Destacar features onde os métodos CONCORDAM (confiança
alta) e onde DISCORDAM (instáveis, investigar).

---

## 5. Rigor e robustez (CRÍTICO)

- **Anti-leakage:** garantir que a análise use só features pré-jogo. NÃO incluir como
  preditor as colunas `*_cur_*` (estatísticas da própria partida) nem os alvos.
- **Estabilidade:** como importância pode variar entre amostras, rodar SHAP/permutação
  com validação cruzada ou múltiplas sementes e reportar média ± desvio. Uma feature
  que só aparece como importante em um fold não é confiável.
- **Escopo correto por alvo:** modelos avançados (escanteios, chutes, cartões) só usam
  os ~4.102 jogos com `has_advanced_stats = 1`. Resultado e gols usam a base ampla.
  Deixar isso explícito em cada análise (quantos jogos sustentam cada ranking).
- **Multicolinearidade:** muitas features são correlacionadas entre si (ex.: várias
  janelas de forma l3/l5/l10). Isso distorce importância (o crédito se divide entre
  features redundantes). Sinalizar grupos de features altamente correlacionadas e,
  se possível, reportar importância agrupada além da individual.
- **Não tocar na produção:** `api/model_artifacts/` e
  `api/international_features_enriched.csv` permanecem intactos.

---

## 6. Entregáveis

1. Um script reproduzível (ex.: `scripts/feature_importance.py`).
2. Um relatório (Markdown) com, para cada alvo:
   - tabela do ranking consolidado (SHAP + permutação, média ± desvio);
   - os gráficos SHAP (summary + dependence das top features);
   - nota sobre quantos jogos sustentam a análise e sobre grupos colineares;
   - para gols e cartões: a mesma análise separada por 1º/2º tempo.
3. Uma **lista enxuta das ~10 features pré-jogo de maior impacto agregado** (úteis e
   editáveis pelo usuário — excluir alvos e features `*_cur_*`), que servirá para a
   etapa de UX. Justificar a escolha com os números.
4. Um resumo executivo: as 3-5 conclusões mais importantes sobre o que determina cada
   alvo (em linguagem clara).

---

## 7. Fora de escopo agora

- Melhorias de UX/UI (será a próxima etapa, usará a lista de 10 features daqui).
- Melhorias de algoritmo (peso temporal, Poisson, calibração) — etapas futuras.
- Re-treino ou promoção de modelos — não fazer.
- Coleta de dados novos — não usar a API.

---

## 8. Antes de implementar

Mostrar um plano curto: estrutura do script, como vai garantir anti-leakage e
estabilidade (CV/sementes), e como vai tratar a multicolinearidade. Aguardar aprovação
antes de rodar a análise completa.
