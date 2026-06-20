# CONTEXTO — Modelos de Contagem para Escanteios (Passo 2)

> Documento autossuficiente para o Claude Code. Leia tudo antes de codar.
> Este é o PASSO 2 do roteiro. Foca SÓ em escanteios. Cartões virão depois, separado.

---

## 1. Objetivo

Substituir a regressão quantílica atual de escanteios por um **modelo de contagem**
(Binomial Negativa), e descobrir empiricamente a melhor arquitetura comparando duas
abordagens. O entregável termina numa **recomendação acionável**: qual modelo usar para
qual mercado de escanteios.

Esta é a continuação direta do Passo 1 (Dixon-Coles para gols, já em produção). Mesma
filosofia: medir com rigor, validar de forma justa, não promover sem prova.

---

## 2. Contexto do que já sabemos (do diagnóstico e do Passo 1)

- O diagnóstico de Fase 1 PROVOU (qui-quadrado) que escanteios são **sobredispersos** →
  a Binomial Negativa ajusta bem, a Poisson é rejeitada, a Normal (implícita na
  regressão quantílica atual) é rejeitada.
- Para GOLS, no Passo 1, a Binomial Negativa "colapsou" em Poisson (parâmetro de
  dispersão r foi para valores altos), porque a variação do lambda entre jogos já
  absorvia a sobredispersão. **Para escanteios isso PODE não acontecer** — a
  sobredispersão pode ser maior e a NB ser usada de fato. REPORTAR o r de dispersão
  para sabermos.
- Importância de features (escanteios): dominado por `elo_home_winprob` (~45%, efeito
  assimétrico não-linear — jogos desiguais inflam escanteios de um lado e zeram do
  outro). Prevê bem o desigual, mal o equilibrado.
- A expectativa de escanteios (lambda) deve ser modelada via features pré-jogo (como no
  Dixon-Coles de gols), NÃO força por time (sobreajuste com seleções).

---

## 3. As três previsões (mercados) a avaliar

Escanteios tem mercados distintos que o usuário pode apostar. Avaliar os TRÊS:
- **Escanteios do mandante** (contagem de um lado)
- **Escanteios do visitante** (contagem de um lado)
- **Escanteios totais do jogo** (soma dos dois lados)

O total NÃO é trivial: somar dois modelos independentes ignora a **correlação entre os
lados**, que em escanteios é **negativa** (jogo dominado = muitos escanteios de um lado,
poucos do outro). Isso afeta a variância/calibração do total. É justamente o que a
comparação abaixo vai testar.

---

## 4. As duas abordagens a comparar

### Abordagem A — Independente (separada)
- Um modelo Binomial Negativa para o mandante, um para o visitante.
- Lambda de cada lado via features pré-jogo.
- **Total** = convolução/soma das duas distribuições assumindo independência.

### Abordagem B — Acoplada (bivariada)
- Modela os dois lados conjuntamente, capturando a correlação entre eles (análogo ao
  acoplamento Dixon-Coles de gols, mas com a correlação que os dados de escanteios
  mostrarem — provavelmente negativa, diferente de gols).
- **Total**, mandante e visitante derivados da distribuição conjunta.
- A forma exata do acoplamento fica a critério do agente (ex.: cópula, correlação
  modelada nos resíduos, ou estrutura tipo Dixon-Coles adaptada) — propor no plano curto.

---

## 5. Como comparar (validação justa — igual ao Passo 1)

- Validação **temporal** (treina no passado, testa no futuro) sobre os jogos com
  escanteios válidos (~4.102), mesmo conjunto de teste para tudo.
- Comparar, para CADA um dos três mercados (mandante, visitante, total):
  - **Modelo atual** (regressão quantílica) vs **Abordagem A** vs **Abordagem B**.
  - Métricas PROBABILÍSTICAS (são o que importa, como no Passo 1): log-loss da
    distribuição de contagem, e calibração das probabilidades de linhas over/under
    (ex.: over 8.5 escanteios totais, over 4.5 do mandante) — Brier, ECE, reliability.
  - Cobertura real do intervalo de 80% E largura média (juntas — cobertura sozinha
    engana, como vimos no diagnóstico).
  - MAE/RMSE como secundárias (não são o foco; esperamos ganho em calibração).
- Reportar o **parâmetro de dispersão r** de cada modelo NB (para saber se a NB está
  sendo usada de fato ou colapsou em Poisson como nos gols).

---

## 6. Anti-leakage e rigor (não repetir erros do projeto)

- Regressores de lambda E parâmetros de dispersão/correlação estimados SÓ no treino.
- Nenhuma feature `*_cur_*` da própria partida.
- **ATENÇÃO ESPECIAL — consistência de dataset:** no Passo 1 descobrimos que a feature
  `shootout_winrate_pre` tinha escala diferente entre o dataset novo e o de produção, e
  isso inflou as previsões em produção. ANTES de treinar, confirme qual dataset será
  usado e que as features estão na escala correta/consistente com o que a produção
  carrega. Não repetir o descasamento de escala.
- Validar o viés global: a média de escanteios prevista deve bater com a média real
  observada (sanidade, como fizemos com gols: média prevista ≈ média real).

---

## 7. Entregável final (acionável)

Um relatório (`comparacao_escanteios.md`) com:
- Tabela das três abordagens (atual / independente / acoplada) × três mercados
  (mandante / visitante / total), nas métricas probabilísticas e de calibração.
- O parâmetro r de dispersão de cada modelo NB.
- Validação de viés global (média prevista vs real).
- **RECOMENDAÇÃO acionável por mercado:** qual modelo usar para escanteios do mandante,
  qual para o visitante, qual para o total. (É plausível que a resposta seja diferente
  por mercado — ex.: independente empata nos lados, acoplada ganha no total. O relatório
  deve dizer claramente.)

NÃO promover à produção ainda — isso é diagnóstico/comparação. A promoção (e a decisão
de arquitetura) será um passo seguinte, após revisão deste relatório.

---

## 8. Fora de escopo agora

- **Cartões** — serão o próximo passo, separado, depois de escanteios fechar. (A
  correlação em cartões provavelmente é POSITIVA, jogo pegado gera cartão dos dois
  lados — comportamento diferente de escanteios. Por isso, alvo separado.)
- Não tocar nos modelos já em produção (gols/resultado Dixon-Coles, e os legados de
  escanteios continuam servindo até a eventual promoção).
- UX, odds de mercado, peso temporal — passos posteriores do roteiro.

---

## 9. Ambiente

- Python 3.12. Libs: scipy (nbinom, distribuições), scikit-learn, statsmodels
  (GLM Binomial Negativa, se útil), numpy, pandas, matplotlib. Instalar o que faltar.
- Reaproveitar a infraestrutura de validação temporal do Passo 1 (`validate_dixon_coles.py`
  como referência de protocolo).
