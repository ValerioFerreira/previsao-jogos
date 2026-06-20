# Estatísticas e Destaques Automáticos das Equipes (UX)

> Especificação da funcionalidade de exibir estatísticas e "destaques" (anomalias)
> de cada equipe na página. Parte do conjunto de melhorias de UX (Passo 3). Custo de
> implementação: baixo-moderado — opera sobre dados já existentes, não treina modelos,
> não gasta cota de API. É uma camada de apresentação.

---

## 1. Data de última atualização dos dados

Exibir na página, de forma visível, a data/hora da última atualização dos dados (vinda do
pipeline diário de coleta). Trivial — o pipeline já sabe quando rodou; basta registrar e
mostrar.

---

## 2. Estatísticas estáticas por equipe (sempre exibidas)

Para cada equipe, mostrar os números dos **últimos 5 confrontos**, nas estatísticas
principais do projeto:
- Gols pró e gols contra
- Chutes e chutes a gol
- Escanteios
- Cartões

São dados diretos, sem cálculo de anomalia. Apenas exibir os valores dos últimos 5 jogos.

---

## 3. Destaques automáticos (anomalias) — o motor "inteligente"

A ideia: detectar automaticamente o que está **fora da curva** no desempenho recente de
cada time e gerar mensagens em linguagem natural. Ex.: "Tomou 5 cartões nos últimos 2
jogos, 4x sua média histórica."

### 3.1 Base de comparação (DECIDIDO)
- A linha de base é a média dos **últimos ~20 jogos** do time em **competições de peso
  similar** (agrupar por nível: competitivo vs amistoso, ou faixa de `tournament_weight`).
  O mais próximo de 20 que houver.
- Razão da escolha: dá volume de dados consistente (~20 jogos quase sempre existem) sem
  misturar contextos incompatíveis (amistoso com mata-mata). Mais robusto que "mesma
  competição exata" (que teria poucos jogos) e mais honesto que "qualquer jogo" (que
  misturaria amistoso com Copa).

### 3.2 Janela de detecção
- Para cada estatística, varrer as combinações de **1 a 5 jogos mais recentes** e medir
  quão anômala cada janela está em relação à base (seção 3.1).
- Estatísticas avaliadas: resultado, gols (pró/contra), chutes, chutes a gol, escanteios,
  cartões.

### 3.3 Como medir "fora da curva" (IMPORTANTE)
- **Ranquear por desvios-padrão** em relação à base, NÃO pela razão "X vezes a média".
  Multiplicadores explodem quando a base é pequena (1 escanteio vs média 0,1 = "10x",
  mas é ruído). Desvios-padrão normalizam pela variabilidade natural da estatística.
- **Exibir** pode usar a forma intuitiva ("4x sua média", "o dobro do normal") porque é
  mais legível — mas a SELEÇÃO/RANQUEAMENTO das anomalias usa desvios-padrão.

### 3.4 Quantas mensagens mostrar (DECIDIDO)
- Mostrar apenas as anomalias que passam de um **limiar de desvio** (a calibrar olhando
  resultados reais). Se houver menos de 3 acima do limiar, mostrar menos. Se não houver
  nenhuma, não mostrar nenhuma — um time "dentro do esperado" não tem destaques, e isso
  é honesto (não inventar alerta onde não há).
- Máximo de 3 mensagens.

### 3.5 Diversidade — uma anomalia por estatística distinta (DECIDIDO)
- As (até) 3 mensagens devem ser de estatísticas DIFERENTES (ex.: uma de cartões, uma de
  gols, uma de escanteios). Nunca três mensagens sobre a mesma estatística.
- Mecânica: para CADA estatística, achar a janela (1-5 jogos) e o desvio mais anômalos
  daquela estatística (seu "pico"); depois ranquear as estatísticas entre si pelo tamanho
  do desvio; mostrar as que passam do limiar, cada uma representada pelo seu pico. Isso
  garante zero redundância e que cada mensagem é o maior destaque da sua estatística.

---

## 4. Construção das mensagens (moldes, não frases fixas)

Em vez de escrever 30-40 frases fixas, usar ~8-10 **moldes preenchíveis** que, combinados
com os números reais, geram dezenas de variações. Ex. de molde:
- "Tomou {n} cartões nos últimos {j} jogos, {mult}x sua média." (acima do normal)
- "Não sofreu gols nos últimos {j} jogos." (sequência defensiva)
- "Conseguiu {n} escanteios nos últimos {j} jogos, bem acima do habitual."
Um molde por (estatística × tipo de desvio: acima / abaixo / sequência). Cobre toda a
variedade desejada com pouco código e fácil manutenção.

---

## 5. Decisões pendentes / a calibrar na implementação
- O valor exato do **limiar de desvio** (quão fora é "fora o suficiente") — ajustar
  olhando exemplos reais para não gerar nem destaque demais nem de menos.
- A definição operacional de "competições de peso similar" (faixas de `tournament_weight`
  ou agrupamento competitivo/amistoso).
- Redação final dos ~8-10 moldes.

---

## 6. Status
DESENHO especificado, não implementado. Faz parte do Passo 3 (UX). Independente dos
modelos — pode ser construído a qualquer momento sobre o CSV existente. O motor de
detecção de anomalias (seção 3) é a maior fatia do esforço e é autocontido (testável
isoladamente, sem risco para os modelos de previsão).
