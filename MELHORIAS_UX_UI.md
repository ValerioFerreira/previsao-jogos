# Melhorias de UX/UI — Interface de Previsão e Apostas

> Documento consolidado das decisões de UX/UI discutidas para a interface (Passo 3 do
> roteiro). Reúne cada recurso, a lógica por trás, e as ressalvas que protegem o usuário.
> Contexto: a interface passa a ser explicitamente voltada a apostas com dinheiro real,
> então honestidade probabilística é requisito, não opção.

---

## Princípio geral que rege todas as decisões

O objetivo final do sistema é gerar **odds justas** (odd = 1/probabilidade). Logo, o que
importa é a **honestidade das probabilidades**, não a aparência de certeza. Vários
recursos abaixo existem justamente para NÃO enganar o usuário — mostrar a probabilidade
real mesmo quando ela é menos atraente. Um app de aposta honesto é o que diz, com
precisão, o quanto NÃO dá para saber.

---

## 1. Slider de probabilidade-alvo → linha correspondente

**O que é:** em vez de o sistema só cuspir "mais de 5 escanteios com 70%", o usuário
escolhe a probabilidade que quer (ex.: 90%) e o sistema responde qual linha entrega
aquela probabilidade (ex.: "mais de 3,5 escanteios").

**Decisão conceitual importante (já resolvida):** abandonamos a ideia de exibir
"confiabilidade" e "chance" como dois números separados. Eles NÃO são variáveis
independentes — ambos derivam da mesma distribuição de probabilidade do modelo. Tentar
mostrá-los como dois botões distintos criaria um número falso. O recurso correto é
único: **probabilidade-alvo → linha**. O usuário desliza a probabilidade, a linha se
ajusta. Quanto maior a probabilidade pedida, mais conservadora a linha.

**Como funciona por baixo:** o modelo (agora NB/Dixon-Coles) produz a distribuição de
contagem. O slider varre a CDF dessa distribuição e encontra a linha que corresponde à
probabilidade escolhida. É matematicamente direto e genuíno.

---

## 2. Entrada alternativa por odd

**O que é:** o usuário pode digitar uma odd em vez de uma probabilidade. Como
odd = 1/probabilidade, pedir "odd 1,50" é pedir "~67% de probabilidade". O sistema acha
a linha que dá essa probabilidade.

**Decisão:** slider de probabilidade e campo de odd são a MESMA ferramenta com rótulos
diferentes, apontando para o mesmo motor. Oferecer os dois como entradas equivalentes.

---

## 3. Combinadas (do mesmo jogo)

**O que é:** o usuário monta uma combinada misturando mercados (resultado, gols, chutes,
escanteios) e o sistema mostra 3 combinações que atingem uma odd-alvo, com alta
probabilidade individual cada.

**Decisão:** combinadas do MESMO jogo (escolha do usuário).

**Ressalva OBRIGATÓRIA (não é opcional):** combinar apostas do mesmo jogo tem um problema
matemático que o sistema precisa mostrar com honestidade:
- As probabilidades se multiplicam para BAIXO: três apostas de 70% NÃO dão "alta
  probabilidade", dão 0,7³ = 34%. A odd sobe (atrativa), mas a chance real despenca.
- Eventos do mesmo jogo são CORRELACIONADOS (ex.: "vitória + mais escanteios do
  favorito" andam juntos), então multiplicar as probabilidades como se fossem
  independentes SUPERESTIMA a chance real da combinada.

**Como exibir (decisão fechada):** mostrar a probabilidade combinada como **"teto
otimista"**, com ressalva explícita de que o valor real tende a ser MENOR por causa da
correlação. Calcular o produto das probabilidades, exibir a odd total E a probabilidade
real estimada lado a lado, marcando claramente que é um teto. É a única forma de oferecer
o recurso sem virar máquina de ilusão.

---

## 4. Edição controlada de ~10 variáveis de alto impacto (substitui edição livre)

**Decisão:** remover os campos de edição livre dos dados das equipes. Substituir por
edição CONTROLADA das features de maior impacto — o usuário pode simular cenários, mas só
nas variáveis que fazem sentido editar.

**Regra de corte:** só features PRÉ-JOGO (estado das equipes na entrada). NUNCA editar os
ALVOS (gols/escanteios/cartões da partida prevista — são o que o modelo produz, não
recebe) nem features `*_cur_*` (estatística da própria partida = leakage).

**As 10 features (definidas pela análise de importância, não chutadas):**
1. `elo_diff` — diferença de Elo (a variável mais importante do sistema).
2. `h2h_home_gd_mean` — saldo de gols médio dos confrontos diretos (intuitivo: freguesia).
3. `home_gf_l5` / `away_gf_l5` — média de gols marcados nos últimos 5 (ataque).
4. `home_ga_l5` / `away_ga_l5` — média de gols sofridos nos últimos 5 (defesa).
5. `tournament_weight` — peso do torneio (amistoso 0,2 → Copa 1,0; afeta chutes/cartões).
6. `neutral` — campo neutro sim/não (remove a vantagem de mando).
7. `home_days_rest` / `away_days_rest` — dias de descanso (desgaste).
8. `home_sb_corners_l5` / `away_sb_corners_l5` — escanteios recentes (tendência).
9. `home_sb_shots_l5` / `away_sb_shots_l5` — chutes recentes (ímpeto ofensivo).
10. `home_sb_cards_l5` / `away_sb_cards_l5` — cartões recentes (disciplina).

**Excluída de propósito:** `matches_played_before` — apareceu como importante para gols,
mas é um proxy de estatura do país (não-editável conceitualmente; o usuário não "edita"
quantos jogos uma seleção já disputou). Fica fora da UI.

---

## 5. Value betting — odd justa vs odd da casa

**O que é (a feature mais valiosa para apostador com método):** o usuário digita a odd
que a casa de apostas está oferecendo; o sistema compara com a probabilidade do modelo e
indica se há "valor" — ou seja, se a probabilidade do modelo é maior do que a odd da casa
implica.

**Por que importa:** é o conceito central de aposta com método. Um modelo bem calibrado
(que é o que construímos) pode apontar divergências exploráveis. MAS: sempre acompanhado
de aviso de risco — value não é garantia.

**Conexão com o roteiro:** isto se relaciona com o Passo 4 (validação contra odds de
mercado). A interface pode mostrar o value, mas só sabemos se ele é REAL depois de validar
o modelo contra odds históricas. Exibir com a devida cautela até essa validação existir.

---

## 6. Indicador de confiabilidade do confronto (volume de dados)

**O que é:** para cada previsão, mostrar quão "dentro do conhecido" o jogo está — se é
entre seleções com muitos dados (previsão mais confiável) ou entre seleções obscuras com
pouca base (previsão frágil). Ajuda o usuário a saber quando confiar mais ou menos.

---

## 7. Histórico de acerto do modelo por mercado

**O que é:** mostrar, honestamente, a performance real do modelo por tipo de mercado
("nas previsões de escanteios, o modelo acertou X% das vezes").

**Ressalva de implementação:** isto EXIGE coletar as previsões ao longo do tempo e
compará-las com os resultados reais — é um recurso que se constrói ao longo de semanas,
não nasce pronto. Decidir se já se deixa a estrutura de logging das previsões pronta
agora, ou se fica para depois.

---

## 8. Avisos de risco visíveis (obrigatório)

Como a interface é explicitamente voltada a apostas com dinheiro real, deixar claro e
VISÍVEL que: são estimativas estatísticas sem garantia; apostar envolve risco de perda;
o modelo tem limites (especialmente em gols/escanteios de jogos equilibrados, que são
inerentemente imprevisíveis). Não é juridiquês defensivo — é a diferença entre uma
ferramenta de análise e algo que empurra alguém a perder dinheiro achando que tem certeza.

---

## Expectativas a comunicar na interface (calibrar o usuário)

Alinhado com a interpretação dos modelos:
- **Resultado e cartões:** previsões mais confiáveis (Elo e contexto são sinais reais).
- **Gols e escanteios de jogos equilibrados:** inerentemente difíceis; o modelo entrega
  probabilidades honestas, não acerto de placar. A interface deve refletir essa incerteza
  (intervalos, "confiança baixa" quando for o caso), não esconder.

---

## Notas sobre dados subjetivos (transparência)

A pergunta surgiu se o modelo usa dados subjetivos. Resposta para referência:
- A esmagadora maioria das features é OBJETIVA (gols, escanteios, Elo — puro cálculo).
- O **rating de jogadores** do API-Football É subjetivo (atribuído por avaliadores), mas
  NÃO está em uso no modelo atual. Seria o candidato a subjetividade se incorporado.
- Semi-subjetivos (decisões de modelagem, não opinião sobre jogos): os K-factors do Elo e
  os pesos de torneio — escolhas humanas sobre como o modelo trata os jogos.

---

## Status

Tudo acima é DESENHO acordado, ainda NÃO implementado. É o Passo 3 do roteiro
(`ESTADO_E_PROXIMOS_PASSOS.md`), a ser feito após os modelos de contagem (escanteios já
validado, cartões pendente). As 10 features editáveis já estão fundamentadas pela análise
de importância e prontas para uso na implementação.
