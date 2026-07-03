"use client";
import React from "react";
import { BookOpen, Layers, Cpu, Gauge, Wrench, PlayCircle } from "lucide-react";

// Índice: grupos -> seções (id + título). Os mesmos ids são usados nos links "Saiba mais"
// espalhados pelo site (InfoTooltip com href="/como-funciona#id").
const TOC: { group: string; icon: React.ReactNode; items: { id: string; title: string }[] }[] = [
  {
    group: "Começando", icon: <PlayCircle className="w-4 h-4" />,
    items: [
      { id: "visao-geral", title: "Visão geral" },
      { id: "analise-independente", title: "Análise Independente" },
      { id: "partida-futura", title: "Análise de Partida Futura" },
      { id: "creditos", title: "Créditos" },
      { id: "promocao", title: 'Promoção "Só Paga se Acertar"' },
      { id: "monte-sua-aposta", title: "Monte sua Aposta" },
    ],
  },
  {
    group: "Mercados", icon: <Layers className="w-4 h-4" />,
    items: [
      { id: "mercado-resultado", title: "Resultado (1X2)" },
      { id: "mercado-btts", title: "Ambas Marcam (BTTS)" },
      { id: "mercado-over25", title: "Mais/Menos de 2,5 gols" },
      { id: "mercado-placar", title: "Placar Exato" },
      { id: "mercado-gols", title: "Gols" },
      { id: "mercado-finalizacoes", title: "Finalizações" },
      { id: "mercado-finalizacoes-gol", title: "Finalizações a Gol" },
      { id: "mercado-escanteios", title: "Escanteios" },
      { id: "mercado-cartoes", title: "Cartões" },
    ],
  },
  {
    group: "Modelos", icon: <Cpu className="w-4 h-4" />,
    items: [
      { id: "modelo-dixon-coles", title: "Dixon-Coles NB (resultado/gols)" },
      { id: "modelo-nb-cascata", title: "NB em cascata (contagem)" },
      { id: "modelo-cards-gp", title: "Generalized Poisson (cartões)" },
      { id: "modelo-calibracao", title: "Calibração das linhas O/U" },
    ],
  },
  {
    group: "Métricas", icon: <Gauge className="w-4 h-4" />,
    items: [
      { id: "metrica-log-loss", title: "Log-loss" },
      { id: "metrica-ece", title: "Calibração (ECE)" },
      { id: "metrica-faixa-odd", title: "Faixa de odd justa" },
      { id: "metrica-confiabilidade", title: "Confiabilidade dos dados" },
    ],
  },
  {
    group: "Ferramentas", icon: <Wrench className="w-4 h-4" />,
    items: [
      { id: "explorador-de-linha", title: "Explorador de Linha" },
      { id: "value-betting", title: "Value Betting" },
      { id: "de-vig", title: "Odd Oposta (De-Vig)" },
      { id: "radar-anomalias", title: "Radar de Anomalias" },
      { id: "alerta-desvio", title: "Alerta de desvio (placar)" },
    ],
  },
];

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 bg-card border border-border/50 rounded-xl p-5">
      <h2 className="text-lg font-heading font-bold mb-2">{title}</h2>
      <div className="text-sm text-muted-foreground leading-relaxed space-y-2">{children}</div>
    </section>
  );
}

export default function ComoFunciona() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-6">
      {/* Índice */}
      <aside className="lg:sticky lg:top-20 lg:self-start">
        <div className="flex items-center gap-2 mb-3">
          <BookOpen className="w-5 h-5 text-primary" />
          <h1 className="text-lg font-bold">Como Funciona?</h1>
        </div>
        <nav className="space-y-4 text-sm">
          {TOC.map((g) => (
            <div key={g.group}>
              <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5">{g.icon} {g.group}</p>
              <ul className="space-y-1 border-l border-border/50 pl-3">
                {g.items.map((it) => (
                  <li key={it.id}><a href={`#${it.id}`} className="text-muted-foreground hover:text-primary transition-colors">{it.title}</a></li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </aside>

      {/* Conteúdo */}
      <div className="space-y-5 max-w-3xl">
        <p className="text-sm text-muted-foreground">
          A <b className="text-foreground">ApostAI</b> é uma plataforma de <b className="text-foreground">análise
          probabilística</b> de partidas de seleções. Ela não “dá palpites”: estima a <b className="text-foreground">distribuição
          de probabilidade</b> de cada mercado com modelos estatísticos, para você comparar com as odds do mercado.
          Os créditos remuneram exclusivamente o uso da Inteligência Artificial; nenhuma previsão garante resultado.
        </p>

        {/* ---------------- Começando ---------------- */}
        <Section id="visao-geral" title="Visão geral">
          <p>Você escolhe uma partida (oficial futura ou uma combinação livre de duas seleções), gera uma <b>análise</b>
            e recebe as probabilidades e odds justas de dezenas de mercados. Para partidas oficiais futuras, você ainda
            pode montar uma aposta na promoção “Só Paga se Acertar”.</p>
        </Section>

        <Section id="analise-independente" title="Análise Independente">
          <p>Você escolhe <b>duas seleções quaisquer</b>, mesmo que não haja um jogo marcado entre elas. É ótimo para
            estudar cenários hipotéticos. Como não existe uma partida oficial associada, <b>não há acompanhamento de
            resultado</b> nem promoção. Consome <b>1 crédito</b> na hora.</p>
        </Section>

        <Section id="partida-futura" title="Análise de Partida Futura">
          <p>Você seleciona uma <b>partida oficial agendada</b>. A análise <b>reserva 1 crédito</b> (não consome ainda) e
            habilita a seção <b>Monte sua Aposta</b>. Após o jogo, o sistema liquida automaticamente sua aposta.</p>
        </Section>

        <Section id="creditos" title="Créditos">
          <p>Cada crédito custa <b>R$ 1,00</b> e remunera o uso da IA. Análise independente <b>consome</b> 1 crédito;
            análise de partida futura <b>reserva</b> 1 crédito. Toda movimentação fica registrada na sua Carteira
            (disponível, reservado e histórico completo).</p>
        </Section>

        <Section id="promocao" title='Promoção "Só Paga se Acertar"'>
          <p>Em análises de partida futura, o crédito reservado só é <b>consumido</b> se a aposta que você montou for
            <b> vencedora</b>. Se ela <b>não</b> vencer (ou não puder ser apurada), o crédito é <b>estornado</b>
            integralmente para a sua carteira. Trata-se de uma campanha comercial de estorno de créditos, não de aposta.</p>
        </Section>

        <Section id="monte-sua-aposta" title="Monte sua Aposta">
          <p>É onde você constrói a aposta da promoção. Filtre por mercado e selecione as opções desejadas — nos mercados
            de linha (Over/Under), elas aparecem em duas colunas, <b>“Acima de”</b> e <b>“Abaixo de”</b>, em ordem
            crescente. A <b>odd combinada</b> é calculada em tempo real e <b>não pode passar de 2,00</b>. Se você não
            escolher nada, o sistema <b>seleciona automaticamente</b> uma aposta com odd próxima de 2,00. Após confirmar,
            a aposta é <b>imutável</b>.</p>
        </Section>

        {/* ---------------- Mercados ---------------- */}
        <Section id="mercado-resultado" title="Resultado (1X2)">
          <p>Probabilidade de <b>vitória do mandante</b>, <b>empate</b> ou <b>vitória do visitante</b>. Sai da matriz
            conjunta de gols do modelo Dixon-Coles.</p>
        </Section>
        <Section id="mercado-btts" title="Ambas Marcam (BTTS)">
          <p>Probabilidade de <b>as duas equipes marcarem</b> pelo menos um gol. Derivada da matriz conjunta (soma das
            células em que mandante ≥ 1 e visitante ≥ 1).</p>
        </Section>
        <Section id="mercado-over25" title="Mais/Menos de 2,5 gols">
          <p>Probabilidade de a partida ter <b>3 ou mais gols</b> (Over) ou <b>2 ou menos</b> (Under). Também vem da
            distribuição conjunta de gols.</p>
        </Section>
        <Section id="mercado-placar" title="Placar Exato">
          <p>Os <b>3 placares mais prováveis</b> segundo a matriz conjunta, com um <b>alerta de desvio</b> quando há
            potencial de placar fora do padrão (ver <a className="text-primary underline" href="#alerta-desvio">Alerta de desvio</a>).</p>
        </Section>
        <Section id="mercado-gols" title="Gols">
          <p>Gols do mandante, do visitante e totais, com recortes por <b>partida inteira, 1º e 2º tempo</b>. Cada linha
            Over/Under sai da distribuição de gols.</p>
        </Section>
        <Section id="mercado-finalizacoes" title="Finalizações">
          <p>Qualquer <b>tentativa de gol</b> (no alvo, para fora, na trave ou bloqueada), por equipe e total. Modelada por
            Binomial Negativa (sobredispersão real).</p>
        </Section>
        <Section id="mercado-finalizacoes-gol" title="Finalizações a Gol">
          <p>Apenas os chutes <b>na direção da baliza</b> que seriam gol sem intervenção do goleiro. Por equipe e total.</p>
        </Section>
        <Section id="mercado-escanteios" title="Escanteios">
          <p>Tiros de canto <b>efetivamente cobrados</b>, por equipe e total. As linhas O/U do total passam por
            <a className="text-primary underline" href="#modelo-calibracao"> calibração</a> adicional.</p>
        </Section>
        <Section id="mercado-cartoes" title="Cartões">
          <p>Cartões <b>amarelos e vermelhos</b> dos jogadores em campo, por equipe, total e por tempo. Modelo Generalized
            Poisson (ver <a className="text-primary underline" href="#modelo-cards-gp">abaixo</a>).</p>
        </Section>

        {/* ---------------- Modelos ---------------- */}
        <Section id="modelo-dixon-coles" title="Dixon-Coles NB (resultado e gols)">
          <p>O coração do sistema. Estima os <b>gols esperados</b> de cada lado com um <b>Gradient Boosting</b> sobre ~158
            variáveis (Elo, forma, mando, descanso, H2H…) e combina numa <b>matriz conjunta</b> de placares, com a
            correção <b>Dixon-Coles</b> para os placares baixos (0-0, 1-1…) e marginais <b>Binomial-Negativa</b>. Dela saem
            resultado, gols, BTTS, over/under e placar exato — todos coerentes entre si.</p>
          <p><b>Por quê:</b> o futebol de seleções é dominado por força relativa (Elo) e tem correlação conhecida nos
            placares baixos; o Dixon-Coles captura exatamente isso.</p>
        </Section>
        <Section id="modelo-nb-cascata" title="NB em cascata (finalizações, a gol, escanteios)">
          <p>Mercados de contagem alta usam <b>Binomial Negativa</b> (variância maior que a média — sobredispersão real),
            em <b>cascata</b>: as finalizações previstas alimentam escanteios e cartões, refletindo o encadeamento do jogo.</p>
        </Section>
        <Section id="modelo-cards-gp" title="Generalized Poisson (cartões)">
          <p>Cartões são contagem baixa; usamos <b>Generalized Poisson</b>, que modela bem a cauda (jogos muito faltosos)
            sem exagerar. Contexto competitivo e histórico das equipes pesam mais que o árbitro (amostra rasa por árbitro
            em seleções).</p>
        </Section>
        <Section id="modelo-calibracao" title="Calibração das linhas O/U">
          <p>As probabilidades Over/Under do <b>total</b> de escanteios, finalizações a gol e cartões passam por uma
            <b> recalibração isotônica</b> validada fora do tempo — quando o modelo diz “70%”, isso acontece ~70% das
            vezes. Melhora a confiabilidade das odds sem alterar a distribuição base.</p>
        </Section>

        {/* ---------------- Métricas ---------------- */}
        <Section id="metrica-log-loss" title="Log-loss (a métrica principal)">
          <p>Mede a probabilidade que o modelo deu ao que <b>de fato aconteceu</b>. Dizer “70%” e acontecer custa pouco;
            dizer “95%” e não acontecer custa muito. Ela pune <b>excesso de confiança errado</b> — justamente o erro mais
            caro em aposta. É por ela que otimizamos os modelos.</p>
        </Section>
        <Section id="metrica-ece" title="Calibração (ECE)">
          <p>Mede se as probabilidades são <b>honestas</b>: entre todas as vezes que o modelo disse ~70%, o evento
            aconteceu perto de 70%? Quanto menor o ECE, mais você pode confiar nas odds justas exibidas.</p>
        </Section>
        <Section id="metrica-faixa-odd" title="Faixa de odd justa">
          <p>É a odd correspondente à probabilidade do modelo, mostrada como uma <b>faixa</b> (da odd com ~7% de margem
            para menos até 1/probabilidade). Serve de referência para comparar com as odds do mercado. A odd justa
            <b> nunca é menor que 1,00</b>. Não inclui margem de casa e não é recomendação de aposta.</p>
        </Section>
        <Section id="metrica-confiabilidade" title="Confiabilidade dos dados">
          <p>Um selo (Alta/Média/Baixa) que indica <b>quanta estatística detalhada</b> (box-score) existe para aquelas
            seleções. Seleções de elite têm cobertura alta; algumas regionais têm cobertura menor, o que aumenta a
            incerteza dos mercados de contagem.</p>
        </Section>

        {/* ---------------- Ferramentas ---------------- */}
        <Section id="explorador-de-linha" title="Explorador de Linha">
          <p>Escolha o mercado, o lado (Over/Under) e deslize a linha para <b>escanear toda a grade</b> de probabilidades e
            odds justas calculadas pela distribuição do modelo. Útil para achar a linha que melhor se ajusta à sua leitura.</p>
        </Section>
        <Section id="value-betting" title="Value Betting — Identificação de Assimetrias">
          <p>Compara a <b>probabilidade do modelo</b> com a <b>odd oferecida</b> pela casa. Se o <b>EV (valor esperado)</b>
            for positivo, existe uma assimetria a seu favor. Também estima o <b>ROI potencial</b>. É uma ferramenta de
            estudo — não garante retorno.</p>
        </Section>
        <Section id="de-vig" title="Odd Oposta (De-Vig)">
          <p>As casas embutem uma <b>margem de lucro</b> nas odds. Informando a odd do <b>lado oposto</b>, o sistema
            remove essa margem (“de-vig”) e estima a <b>probabilidade real implícita</b> da casa, para uma comparação
            mais justa com o modelo.</p>
        </Section>
        <Section id="radar-anomalias" title="Radar de Anomalias">
          <p>Destaca <b>desvios estatísticos</b> recentes de cada seleção (sequências fora do padrão, variações bruscas de
            desempenho) que ajudam a contextualizar a previsão.</p>
        </Section>
        <Section id="alerta-desvio" title="Alerta de desvio (Placar Exato)">
          <p>No Placar Exato, sinaliza quando há <b>potencial de placar fora do padrão</b> — por forte favoritismo de um
            lado ou por muitos gols esperados (alta probabilidade de 4+ gols).</p>
        </Section>

        <p className="text-xs text-muted-foreground pt-2">
          As odds justas são referência analítica, sem margem de casa, e não constituem recomendação de aposta. Jogue com responsabilidade.
        </p>
      </div>
    </div>
  );
}
