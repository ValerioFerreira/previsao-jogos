# CONTEXTO — Diagnóstico dos Modelos de Gols e Escanteios (Fase 1)

> Documento autossuficiente para o Claude Code. Leia tudo antes de codar.
> Esta é a FASE 1 (diagnóstico) de um plano maior de melhoria. NÃO implementa modelos
> novos ainda — apenas MEDE onde estamos, para decidir o que vale a pena melhorar.

---

## 1. Por que esta fase existe

Os modelos de gols e escanteios são os mais fracos do sistema (a análise de importância
mostrou que gols se apoia num proxy de estatura por falta de sinal melhor, e escanteios
é dominado pela assimetria de Elo). Antes de trocar/melhorar esses modelos, precisamos
de um EXAME que diga, com números:
1. O quão melhor (ou não) o modelo atual é comparado a uma baseline ingênua.
2. O quão bem calibradas estão as probabilidades (crítico, porque o objetivo final é odds).

Sem esse diagnóstico, otimizaríamos às cegas. O resultado desta fase define as próximas.

REGRA DE OURO do projeto: uma mudança de cada vez, validada. Esta fase NÃO altera
modelos de produção nem de desenvolvimento — só lê, mede e relata.

---

## 2. Estado atual (contexto)

- Base: `international_features_enriched_apifootball.csv` (~9.976 jogos; 4.102 com
  estatísticas avançadas completas — chutes, escanteios, cartões).
- Modelos de desenvolvimento em `api/model_artifacts_apifootball/`: regressão
  quantílica (GradientBoosting q10/q50/q90) para total de gols, escanteios
  mandante/visitante, finalizações, cartões; classificadores para resultado/BTTS/over2.5.
- Validação justa já estabelecida em scripts anteriores: validação cruzada 5-fold e
  validação TEMPORAL (treina no passado, testa no futuro), sempre sobre o mesmo
  conjunto de teste para comparações. REUTILIZAR essa infraestrutura.

---

## 3. O que medir (entregáveis do diagnóstico)

Para os alvos **total de gols**, **escanteios mandante** e **escanteios visitante**
(e, se trivial, finalizações e cartões), calcular e reportar:

### 3.1 Baselines ingênuas (o juiz de tudo)
Comparar o erro do modelo atual contra baselines simples, na MESMA validação temporal:
- **Média global:** prever sempre a média do alvo no treino.
- **Média condicional simples:** prever a média do alvo condicionada a 1-2 variáveis
  óbvias (ex.: média de gols por tipo de torneio; média de escanteios do time mandante).
- Reportar MAE e RMSE do modelo atual E de cada baseline, lado a lado.
- **Conclusão explícita:** quanto o modelo atual ganha (ou não) sobre a baseline. Se o
  ganho for marginal, dizer claramente — é informação valiosa, não vergonha.

### 3.2 Calibração das probabilidades (o que mais importa p/ odds)
Os alvos numéricos têm quantis (q10/q50/q90) → dá para derivar probabilidades de
over/under em linhas. Os classificadores (resultado, BTTS, over 2.5) já dão probabilidade.
- Gerar **reliability diagrams** (gráfico de calibração: probabilidade prevista no eixo
  X, frequência real observada no eixo Y; a diagonal perfeita = bem calibrado).
- Calcular **métricas de calibração**: Brier score e/ou Expected Calibration Error (ECE).
- Verificar a **cobertura real dos intervalos quantílicos**: quando o modelo diz
  "intervalo de 80%", o valor real cai dentro 80% das vezes? Já vimos coberturas de
  ~69% (mal calibrado, overfit) a ~79% (bom). Reportar por alvo.
- Para over/under de gols especificamente: a probabilidade prevista de "over 2.5" bate
  com a frequência observada? Plotar.

### 3.3 Diagnóstico de resíduos (onde o modelo erra)
- Onde o erro é maior: jogos equilibrados vs desequilibrados? Competições específicas?
  Placares altos (a "cauda" de jogos 5+ gols)? 
- Para gols/escanteios, checar se a distribuição prevista tem a forma certa: contagens
  reais seguem algo próximo de Poisson/Binomial Negativa. O modelo atual (regressão
  quantílica) captura a assimetria e a cauda, ou subestima jogos de placar alto?
- Isso indica se vale migrar para um modelo de contagem (Poisson/Dixon-Coles) depois.

---

## 4. Rigor (não repetir erros do projeto)

- Validação TEMPORAL como referência principal (reflete uso real: prever o futuro).
- Mesmo conjunto de teste para modelo e baselines (comparação justa).
- Anti-leakage: nenhuma feature `*_cur_*` da própria partida. Só pré-jogo.
- Reportar média ± desvio entre folds onde aplicável (estabilidade).

---

## 5. Entregável final

Um relatório (`diagnostico_gols_escanteios.md`) com, por alvo:
- Tabela: modelo atual vs baselines (MAE, RMSE) — e a conclusão de quanto o modelo
  realmente agrega sobre o ingênuo.
- Reliability diagrams salvos como imagem + Brier/ECE.
- Cobertura real dos intervalos de 80%.
- Diagnóstico de resíduos: onde erra mais, e se a forma da distribuição sugere um
  modelo de contagem.
- **Recomendação fundamentada:** com base nesses números, o que tem maior potencial de
  ganho — trocar para modelo de contagem (Poisson/Dixon-Coles)? calibrar? adicionar
  features de estilo? Ranquear por retorno esperado.

NÃO implementar as melhorias ainda. Só diagnosticar e recomendar. As próximas fases
serão decididas a partir deste relatório.

---

## 6. Fora de escopo agora

- Não implementar Dixon-Coles, Poisson, calibração ou features novas nesta fase.
- Não tocar em produção (`api/model_artifacts/`) nem re-treinar para produção.
- Não mexer na interface.

---

## 7. Ambiente

- Python 3.12. Libs: scikit-learn (calibration_curve, brier_score_loss), pandas, numpy,
  matplotlib, scipy (distribuições de contagem). Instalar o que faltar.
- Trabalhar sobre a base e os modelos de desenvolvimento (API-Football).
