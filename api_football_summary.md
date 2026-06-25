# Análise da Documentação da API-Football

Este documento detalha as informações solicitadas sobre a API-Football, incluindo como obter logos e imagens, dados de partidas futuras e uma sugestão abrangente para uma página de estatísticas.

## 1. Como pegar os logos/brasões/imagens das equipes e dos jogadores

A documentação indica URLs diretas para acessar os logos de equipes e fotos de jogadores. É importante notar que essas chamadas não contam para a cota diária de requisições, mas estão sujeitas a limites de taxa por segundo e por minuto. Recomenda-se salvar esses dados localmente (utilizando uma CDN, por exemplo) para otimizar a experiência do usuário e evitar lentidão.

*   **Logos de Equipes:**
    Para obter o logo de uma equipe, utilize a seguinte URL, substituindo `{team_id}` pelo ID da equipe:
    `https://media.api-sports.io/football/teams/{team_id}.png`

    Os IDs das equipes podem ser obtidos através do endpoint `/teams` [^1].

*   **Fotos de Jogadores:**
    Para obter a foto de um jogador, utilize a seguinte URL, substituindo `{player_id}` pelo ID do jogador:
    `https://media.api-sports.io/football/players/{player_id}.png`

    Os IDs dos jogadores podem ser obtidos através do endpoint `/players/profiles` [^1].

## 2. Partidas Futuras e seus Dados

A API-Football oferece a possibilidade de consultar partidas futuras através do endpoint `/fixtures`. Existem diversos parâmetros que permitem filtrar e obter informações sobre jogos que ainda não ocorreram.

*   **Como identificar partidas futuras:**
    O endpoint `/fixtures` permite filtrar partidas por status. As partidas futuras são identificadas pelos seguintes status:
    *   `NS`: Not Started (Não Iniciada)
    *   `TBD`: Time To Be Defined (Horário a Ser Definido) - Partidas agendadas, mas com data e hora ainda desconhecidas.
    *   `PST`: Match Postponed (Partida Adiada) - Adiada para outro dia; o status mudará para `NS` quando a nova data for conhecida.

    Você pode usar o parâmetro `status` com um ou mais desses valores para buscar partidas futuras. Por exemplo, `status=NS` ou `status=NS-PST` [^1].

*   **Parâmetros para buscar partidas futuras:**
    *   `next={X}`: Retorna as próximas `X` partidas disponíveis. Exemplo: `get("https://v3.football.api-sports.io/fixtures?next=15")`
    *   `date={YYYY-MM-DD}`: Retorna partidas para uma data específica. Exemplo: `get("https://v3.football.api-sports.io/fixtures?date=2026-06-25")`
    *   `league={id}&season={YYYY}`: Filtra partidas futuras por liga e temporada.
    *   `team={id}`: Filtra partidas futuras de uma equipe específica.
    *   `from={YYYY-MM-DD}&to={YYYY-MM-DD}`: Filtra partidas futuras dentro de um intervalo de datas.

*   **Dados disponíveis para partidas futuras:**
    Para partidas futuras, os dados disponíveis incluem informações básicas como:
    *   `fixture.id`: ID da partida.
    *   `fixture.date`: Data e hora da partida.
    *   `fixture.timestamp`: Timestamp da partida.
    *   `fixture.status`: Status da partida (NS, TBD, PST, etc.).
    *   `league.id`, `league.name`, `league.country`, `league.logo`: Informações da liga.
    *   `teams.home.id`, `teams.home.name`, `teams.home.logo`: Informações do time da casa.
    *   `teams.away.id`, `teams.away.name`, `teams.away.logo`: Informações do time visitante.
    *   `venue.id`, `venue.name`, `venue.city`: Informações do estádio.
    *   `goals.home`, `goals.away`: Gols (serão nulos para partidas futuras).
    *   `score.halftime`, `score.fulltime`, `score.extratime`, `score.penalty`: Placar (serão nulos para partidas futuras).

    Para partidas futuras, informações como eventos, escalações, estatísticas e jogadores em campo não estarão disponíveis até que a partida ocorra ou esteja em andamento [^1].

## 3. Sugestão para uma Página de "Estatísticas" completa

Para uma página de "Estatísticas" que permita ao usuário selecionar uma partida e obter **TODAS** as informações que a API pode fornecer, o agente de IA deve integrar dados de vários endpoints. A estrutura sugerida abaixo visa apresentar uma visão completa de uma partida.

### Estrutura da Página de Estatísticas por Partida

1.  **Informações Básicas da Partida (Endpoint: `/fixtures?id={fixture_id}`)**
    *   **Detalhes da Partida:**
        *   Data e Hora da Partida
        *   Liga e Temporada (Nome, País, Logo)
        *   Estádio (Nome, Cidade)
        *   Árbitro
        *   Status da Partida (Ex: `FT` - Full Time, `NS` - Not Started, `LIVE` - In Progress)
    *   **Times:**
        *   Time da Casa (Nome, Logo)
        *   Time Visitante (Nome, Logo)
    *   **Placar:**
        *   Placar Final (Gols do Time da Casa, Gols do Time Visitante)
        *   Placar por Tempo (Primeiro Tempo, Segundo Tempo, Prorrogação, Pênaltis - se aplicável)

2.  **Estatísticas da Partida (Endpoint: `/fixtures/statistics?fixture={fixture_id}`)**
    *   **Estatísticas Gerais por Time:**
        *   Posse de Bola
        *   Total de Chutes (no gol, fora do gol, bloqueados)
        *   Chutes Dentro da Área / Fora da Área
        *   Faltas
        *   Escanteios
        *   Impedimentos
        *   Cartões Amarelos
        *   Cartões Vermelhos
        *   Defesas do Goleiro
        *   Passes (total, precisão)
        *   Ataques (perigosos, totais)

3.  **Eventos da Partida (Endpoint: `/fixtures/events?fixture={fixture_id}`)**
    *   **Linha do Tempo de Eventos:**
        *   Gols (minuto, jogador, tipo de gol - pênalti, gol contra, etc., assistente)
        *   Cartões (minuto, jogador, tipo de cartão - amarelo, vermelho)
        *   Substituições (minuto, jogador que sai, jogador que entra)
        *   Eventos VAR (se aplicável)

4.  **Escalações e Formações (Endpoint: `/fixtures/lineups?fixture={fixture_id}`)**
    *   **Time da Casa e Visitante:**
        *   Formação Tática
        *   Jogadores Titulares (Nome, Posição, Número da Camisa, Foto do Jogador)
        *   Jogadores Reservas (Nome, Posição, Número da Camisa, Foto do Jogador)
        *   Treinador (Nome, Foto do Treinador)

5.  **Estatísticas de Jogadores na Partida (Endpoint: `/fixtures/players?fixture={fixture_id}`)**
    *   **Desempenho Individual por Jogador (para cada time):**
        *   Minutos Jogados
        *   Gols (total, assistências, gols sofridos pelo goleiro)
        *   Chutes (total, no gol)
        *   Passes (total, precisão)
        *   Desarmes
        *   Interceptações
        *   Dribles (tentados, bem-sucedidos)
        *   Faltas (cometidas, sofridas)
        *   Cartões (amarelos, vermelhos)
        *   Pênaltis (marcados, defendidos)

6.  **Previsões e Odds (Endpoints: `/predictions?fixture={fixture_id}` e `/odds?fixture={fixture_id}`)**
    *   **Previsões da Partida (se disponível):**
        *   Resultado mais provável
        *   Probabilidades de vitória (casa, empate, fora)
    *   **Odds de Apostas (Pré-jogo):**
        *   Casas de Apostas disponíveis
        *   Tipos de Aposta (Resultado Final, Mais/Menos Gols, Ambas Marcam, etc.)
        *   Odds para cada resultado/aposta

### Fluxo de Dados para o Agente de IA

1.  **Seleção da Partida:** O usuário seleciona uma partida (provavelmente por `fixture_id`).
2.  **Chamadas à API:** O agente faria as seguintes chamadas (substituindo `{fixture_id}` pelo ID da partida selecionada):
    *   `GET https://v3.football.api-sports.io/fixtures?id={fixture_id}`
    *   `GET https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}`
    *   `GET https://v3.football.api-sports.io/fixtures/events?fixture={fixture_id}`
    *   `GET https://v3.football.api-sports.io/fixtures/lineups?fixture={fixture_id}`
    *   `GET https://v3.football.api-sports.io/fixtures/players?fixture={fixture_id}`
    *   `GET https://v3.football.api-sports.io/predictions?fixture={fixture_id}` (se desejar incluir previsões)
    *   `GET https://v3.football.api-sports.io/odds?fixture={fixture_id}` (se desejar incluir odds)
3.  **Processamento e Exibição:** O agente processaria as respostas JSON de cada endpoint e as apresentaria de forma organizada na página de estatísticas, utilizando os logos de equipes e fotos de jogadores obtidos pelas URLs diretas.

É crucial que o agente de IA implemente um tratamento robusto para casos onde os dados podem não estar disponíveis (por exemplo, previsões ou odds para todas as partidas, ou estatísticas detalhadas para jogos muito antigos ou de ligas menores). Além disso, a documentação menciona a importância de gerenciar a chave da API (`x-apisports-key`) de forma segura, preferencialmente no backend, e considerar o cache de dados para otimizar o uso da cota diária [^1].

## Referências

[^1]: [API-Football Documentation](file:///home/ubuntu/upload/api-football-html.txt) (Documentação fornecida pelo usuário))
