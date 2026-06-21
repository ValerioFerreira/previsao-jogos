# Estado do Projeto e Próximos Passos — Previsão de Jogos de Seleções

> Mapa consolidado para retomar o projeto sem reabrir tudo. Resume o que já foi feito,
> o estado atual dos modelos, e a sequência de próximos passos acordada.

> **PONTO DE RETOMADA:** Passos 1, 1.5, 2/2c (escanteios), 2b (cartões) e a
> **modernização de chutes (NB + time decay)** concluídos. **TODOS os mercados de
> contagem agora usam distribuição própria** (Dixon-Coles em gols/resultado; NB em
> escanteios/cartões/chutes) — não há mais mercado legado (quantílica/Normal aposentadas).
> **Peso temporal e mando/competição foram TESTADOS** (ver achados abaixo): o time decay
> só ajuda chutes (aplicado lá, H=2); nos demais alvos foi neutro/negativo, então NÃO
> promovido globalmente. Próximo: **Passo 3 (UX)** ou validação contra odds de mercado.

---

## Onde o projeto está (estado atual)

- **Fonte de dados:** migração COMPLETA de StatsBomb para **API-Football**. O StatsBomb
  foi a base inicial e está só arquivado como backup (`model_artifacts_backup/`). A
  produção roda 100% na API. Base: **9.511 jogos** crus (gzip, com `players`),
  **4.102 jogos** com estatísticas avançadas completas, integrados à âncora martj42
  (99,1% de aproveitamento).
- **PRODUÇÃO ATUAL (tudo na API, um único `meta.json` regendo as features):**
  - **Resultado (H/D/A), gols, BTTS, over/under:** servidos pelo **Dixon-Coles NB**,
    todos derivados da mesma matriz conjunta (sistema coerente, uma voz só).
  - **Escanteios (mandante/visitante/total):** Binomial Negativa independente — PMF real,
    linhas O/U e odds extraídas da CDF (`corners_nb.joblib`).
  - **Cartões (mandante/visitante/total):** NB independente, exposta desde o Passo 2b —
    na prática **Poisson** (r colapsou em ~1000; sem sobredispersão real), o ganho vem da
    distribuição de contagem própria vs a Normal (`cards_nb.joblib`).
  - **Chutes (total):** NB independente (r≈18/16, sobredispersão real) **com time decay
    H=2** — único alvo onde o peso temporal ajuda (`shots_nb.joblib`). Aposentou a
    quantílica + Normal de chutes; agora expõe PMF + linhas O/U + odds da CDF.
  - Backups duplos preservados: `model_artifacts_backup/` (StatsBomb original) e
    `model_artifacts_pre_unificacao/` (estado pré-migração).
- **Dixon-Coles (gols) — validado out-of-sample na base da API:** ganho robusto no
  **resultado H/D/A** (log-loss 0,874→0,830; ECE 7,57%→3,16%) e no log-loss de gols;
  BTTS/over equivalentes. Ganho vem do **acoplamento Dixon-Coles**, não da Binomial
  Negativa (r convergiu para região quase-Poisson). **JÁ EM PRODUÇÃO.**

## Viés temporal — INVESTIGADO e resolvido (peso temporal testado)

O viés levemente negativo observado (gols −0,10, chutes −0,52, escanteios −0,26/−0,19) foi
atacado com **time decay (sample_weight = 0,5^(Δdias/H))** e medido por alvo. **Conclusão:**
- **Chutes:** o viés era genuinamente temporal e grande (−0,80). O decay **H=2** corta para
  −0,31 e despenca o ECE (5,6%→2,5%). **Aplicado** (`shots_nb.joblib`).
- **Gols:** o viés (−0,11) é **invariante ao decay** — não é tendência temporal, é estrutural.
- **Escanteios/cartões:** viés já ~zero no split; o decay no máximo ajuda o ECE marginalmente
  em H moderado e **piora** com H curto. **Não promovido.**
Ou seja, a "tendência temporal" era majoritariamente um efeito de chutes. Mando triplo e
peso de competição também foram testados: 3b (peso de competição) negativo; 3a (mando) tem
resíduo real em escanteios no campo neutro (~0,30) — registrado como melhoria potencial
localizada, não promovida. Os experimentos estão em `scripts/experiment_*` (working tree).

---

## Decisões estruturais já tomadas (não reabrir)

- Apenas **seleções masculinas adultas** (CHAN excluído). Clubes seriam projeto à parte.
- Coletor com cache por jogo, retomada e auto-regulação por headers de rate limit.
- Atribuição de estatísticas por **nome de país** (não home/away) — robusta a mando
  invertido por design (auditado: 0 jogos com mando invertido real).
- Validação SEMPRE com mesmo conjunto de teste para os dois modelos, modalidades
  5-fold aleatória E temporal. Métrica probabilística (log-loss/Brier/ECE) é a que
  importa, não MAE, para alvos perto do teto de previsibilidade.
- Arquitetura híbrida por mercado: melhor modelo para cada alvo, não um modelo único.

---

## Interpretação-chave dos modelos (calibrar expectativas)

- **Forte e genuíno:** resultado (Elo é preditor real), cartões (contexto competitivo).
- **Fraco por natureza:** gols (sinal escasso, apoiado em proxy de estatura;
  ~2% melhor que baseline ingênua) e escanteios em jogos equilibrados (Elo só prevê
  bem os desiguais).
- Há um **teto de previsibilidade real** do futebol. O ganho realista está na
  **calibração das probabilidades** (e portanto na honestidade das odds), não no
  acerto pontual de placar. Distribuição correta dos dados: **Binomial Negativa**
  (provado por qui-quadrado); Poisson e Normal foram rejeitadas.

---

## Próximos passos (sequência acordada, um de cada vez)

### Passo 1 — Promover Dixon-Coles à produção  ✅ CONCLUÍDO
DC promovido como modelo de resultado/gols/BTTS/over (matriz única). Pegou e corrigiu um
bug de inflação de gols (descasamento de escala da feature `shootout_winrate_pre` entre
datasets). Coerência e não-regressão validadas.

### Passo 1.5 — Unificação 100% na base da API  ✅ CONCLUÍDO
Migração final: toda a produção passou a rodar na base da API com um único `meta.json`.
Backups duplos preservados. Revalidação out-of-sample confirmou que o ganho do Dixon-Coles
se mantém (ECE resultado 3,16%) e que não há inflação nos mercados de contagem.

### Passo 2 — Binomial Negativa para ESCANTEIOS  ✅ CONCLUÍDO
Comparadas 3 abordagens (quantílico atual / NB independente / NB acoplada) × 3 mercados.
**Resultado:** a NB tem sobredispersão real em escanteios (r ~20-29, NÃO colapsou em
Poisson como gols → NB usada de fato). A correlação entre lados é negativa mas FRACA
(β=-0,04); o acoplamento NÃO compensou — a NB independente (convolução) ganhou no total
(ECE 2,75% vs 5,11%) e no mandante, e empatou no visitante (4ª casa decimal).
**Decisão:** NB independente para os três mercados; acoplamento aposentado para
escanteios. A NB independente bate a regressão quantílica atual em log-loss e ECE nos
três mercados.

### Passo 2c — Promover escanteios à produção  ✅ CONCLUÍDO
A NB independente de escanteios foi promovida com sucesso.
- O modelo foi re-treinado na base inteira com $r_H=18.20$ e $r_A=16.70$.
- O `predictor.py` e `odds.py` foram atualizados para expor a PMF real e calcular as odds e
  linhas de over/under diretamente da CDF da NB (aposentando a aproximação Normal).
- Validação e testes HTTP de não-regressão concluídos com sucesso.

### Passo 2b — Cartões  ✅ CONCLUÍDO (promovido)
Comparação independente vs acoplado vs quantílica nos 3 mercados. **Correlação CONFIRMADA
positiva** (β=+0,072, ao contrário dos escanteios) — mas fraca: o acoplado empatou a
independente em log-loss e só ajudou marginalmente o ECE do total. **Decisão: NB independente
nos três mercados** (a NB bate a quantílica em log-loss e ECE em tudo). **Achado honesto:**
o r colapsou (≈1000) → cartões NÃO têm sobredispersão real (como gols, não como escanteios);
o ganho vem da distribuição de contagem própria, não da NB. `cards_nb.joblib` treinado na
base inteira; exposto no `predictor.py`/`odds.py` (PMF + linhas O/U 1.5–6.5 + odds da CDF)
PELA PRIMEIRA VEZ. Não-regressão + HTTP validados. Caveat: intervalo 80% coarse (contagem
baixa, sobre-cobre ~92%); estimativa e linhas O/U confiáveis.

### Passo 3 — Melhorias de UX/UI
Já desenhadas. Inclui: slider de probabilidade-alvo → linha correspondente (e entrada
alternativa por odd); combinadas do MESMO jogo exibindo probabilidade combinada real
como "teto otimista" com ressalva de correlação; remoção de campos de edição livre,
substituídos por edição controlada das **10 features de alto impacto** já definidas
pela análise de importância (excluindo alvos e `*_cur_*`); comparação odd-justa vs
odd-da-casa (value betting); indicador de confiabilidade do confronto (volume de dados);
avisos de risco visíveis. As 10 features: elo_diff, h2h_home_gd_mean, gf_l5, ga_l5,
tournament_weight, neutral, days_rest, sb_corners_l5, sb_shots_l5, sb_cards_l5.

### Passo 4 — Validação contra odds de mercado
A fronteira que responde "o sistema tem valor de aposta real?". Exige coletar histórico
de odds (nova coleta). Compara as probabilidades do modelo contra as implícitas nas odds
das casas, para detectar divergências exploráveis (value). É provavelmente o trabalho
mais importante que resta para o objetivo de apostas, e o ainda-não-respondido.

### Passo 5 — Peso temporal (EWMA por dias)
Refino de retorno incerto. Para seleções, decaimento por DIAS (não por número de jogos),
já que jogam esparso. Provavelmente move pouco gols/cartões (perto do teto), mas pode
ajudar a forma recente que alimenta resultado/escanteios. Deixado por último de propósito.

---

## Disciplina que protegeu o projeto (manter)

- Uma mudança de cada vez, validada antes de seguir.
- Pedir ao agente "plano curto antes de implementar" e revisar antes de aprovar.
- Pedir ao agente para sinalizar resultados "bons demais" — isso pegou: bug de índice
  no gamelog, dois vieses de amostra (falso salto de 58%), risco de mando invertido,
  o parâmetro r no teto do otimizador, e a inflação de gols por descasamento de escala
  de feature entre datasets (só apareceu no teste de fumaça com previsões reais).
- Nunca promover à produção sem validação justa (mesmo conjunto de teste) que sustente.
- Chave de API só via variável de ambiente, nunca em arquivo/commit.
