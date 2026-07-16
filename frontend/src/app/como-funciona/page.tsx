"use client";
import React from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { BookOpen, Layers, Cpu, Gauge, Wrench, PlayCircle, Trophy, Sparkles, ArrowRight, RotateCcw, CheckCircle2 } from "lucide-react";

// Card de destaque da oferta "ParcerIA" — no topo da página, com movimento e fonte diferenciada.
function ParcerIAHighlight() {
  return (
    <motion.div
      initial={{ opacity: 0, y: -12, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="relative overflow-hidden rounded-2xl border border-emerald-500/40 bg-gradient-to-br from-emerald-500/15 via-cyan-500/10 to-transparent p-6 sm:p-7 shadow-xl shadow-emerald-500/10"
    >
      {/* brilho animado de fundo */}
      <motion.div
        aria-hidden
        animate={{ opacity: [0.25, 0.55, 0.25], scale: [1, 1.15, 1] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
        className="pointer-events-none absolute -top-20 -right-16 w-56 h-56 rounded-full bg-emerald-500/25 blur-3xl"
      />
      <motion.div
        aria-hidden
        animate={{ opacity: [0.15, 0.4, 0.15] }}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut", delay: 1 }}
        className="pointer-events-none absolute -bottom-24 -left-10 w-56 h-56 rounded-full bg-cyan-500/20 blur-3xl"
      />

      <div className="relative">
        <motion.span
          animate={{ scale: [1, 1.06, 1] }}
          transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
          className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/20 border border-emerald-500/40 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-emerald-300"
        >
          <Sparkles className="w-3.5 h-3.5" /> Oferta em destaque
        </motion.span>

        <h2 className="mt-3 font-heading font-extrabold leading-tight flex items-center gap-2 text-3xl sm:text-4xl">
          <Trophy className="w-8 h-8 text-amber-400 shrink-0" />
          <span className="bg-gradient-to-r from-emerald-300 via-cyan-300 to-emerald-300 bg-clip-text text-transparent">
            ParcerIA
          </span>
        </h2>
        <p className="mt-1 font-heading text-lg sm:text-xl font-bold text-foreground">Você só paga se ganhar!</p>

        <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
          Ao analisar uma <b className="text-foreground">partida oficial agendada</b>, você reserva <b className="text-foreground">1 crédito</b> e
          monta uma aposta combinando os palpites da própria análise (odd máxima de <b className="text-foreground">2,00</b>).
          O sistema acompanha a partida para ver o resultado:
        </p>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-emerald-300"><CheckCircle2 className="w-4 h-4" /> Se sua aposta bater</p>
            <p className="text-xs text-muted-foreground mt-1">O crédito é consumido — pô, a gente ajudou né! 😅</p>
          </div>
          <div className="rounded-xl border border-cyan-500/30 bg-cyan-500/10 p-3">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-cyan-300"><RotateCcw className="w-4 h-4" /> Se sua aposta não bater</p>
            <p className="text-xs text-muted-foreground mt-1">Não fique triste, seu crédito é estornado e você pode fazer uma nova análise. A gente torce pra que dê mais sorte! 🍀🤞</p>
          </div>
        </div>

        <div className="mt-4 rounded-xl bg-background/40 border border-border/50 p-3">
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1.5">Exemplos</p>
          <ul className="space-y-1.5 text-sm">
            <li className="flex items-start gap-2"><span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" /><span><b className="text-foreground">Brasil não perde</b> + <b className="text-foreground">Mais de 2,5 gols</b> — se os dois se confirmarem, o crédito é consumido; senão, estornado.</span></li>
            <li className="flex items-start gap-2"><span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" /><span><b className="text-foreground">Ambas Marcam: Sim</b> + <b className="text-foreground">Mais de 8,5 escanteios</b> — combine mercados da análise; a odd combinada é calculada de forma justa (até 2,00).</span></li>
          </ul>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Link href="/" className="inline-flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/40 transition-shadow">
            Selecionar Partida Agendada <ArrowRight className="w-4 h-4" />
          </Link>
          <a href="#promocao" className="text-sm font-medium text-primary hover:underline">Ver as regras completas ↓</a>
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground italic">
          Campanha promocional da ApostaInfo — não representa uma aposta ou jogo de azar, e não envolve pagamento de prêmios em dinheiro.
        </p>
      </div>
    </motion.div>
  );
}

// Índice: grupos -> seções (id + título). Os mesmos ids são usados nos links "Saiba mais"
// espalhados pelo site (InfoTooltip com href="/como-funciona#id").
const TOC: { group: string; icon: React.ReactNode; items: { id: string; title: string }[] }[] = [
  {
    group: "Começando", icon: <PlayCircle className="w-4 h-4" />,
    items: [
      { id: "visao-geral", title: "Visão Geral" },
      { id: "analise-independente", title: "Análise Independente" },
      { id: "partida-futura", title: "Análise de Partida Futura" },
      { id: "creditos", title: "Créditos" },
      { id: "promocao", title: 'Promoção "ParcerIA"' },
      { id: "monte-sua-aposta", title: "Monte sua Aposta" },
    ],
  },
  {
    group: "Mercados", icon: <Layers className="w-4 h-4" />,
    items: [
      { id: "mercado-resultado", title: "Resultado (1X2)" },
      { id: "mercado-btts", title: "Ambas Marcam (BTTS)" },
      { id: "mercado-over25", title: "Mais/Menos de 2,5 Gols" },
      { id: "mercado-placar", title: "Placar Exato" },
      { id: "mercado-gols", title: "Gols" },
      { id: "mercado-finalizacoes", title: "Finalizações" },
      { id: "mercado-finalizacoes-gol", title: "Finalizações a Gol" },
      { id: "mercado-escanteios", title: "Escanteios" },
      { id: "mercado-cartoes", title: "Cartões" },
      { id: "mercado-odds-justas", title: "Odds Justas dos Mercados" },
    ],
  },
  {
    group: "Como os modelos funcionam", icon: <Cpu className="w-4 h-4" />,
    items: [
      { id: "modelo-dixon-coles", title: "Dixon-Coles + Binomial Negativa" },
      { id: "modelo-cascata", title: "Modelagem em Cascata" },
      { id: "modelo-cartoes", title: "Modelo de Cartões" },
      { id: "modelo-calibracao", title: "Calibração das Linhas O/U" },
      { id: "metrica-log-loss", title: "Log-Loss" },
      { id: "metrica-ece", title: "Calibração (ECE)" },
      { id: "modelo-varios", title: "Por que vários modelos?" },
      { id: "modelo-aprendizado", title: "IA e Aprendizado Contínuo" },
    ],
  },
  {
    group: "Ferramentas e Recursos", icon: <Wrench className="w-4 h-4" />,
    items: [
      { id: "metrica-faixa-odd", title: "Faixa de Odd Justa" },
      { id: "metrica-confiabilidade", title: "Confiabilidade dos Dados" },
      { id: "explorador-de-linha", title: "Explorador de Linha" },
      { id: "value-betting", title: "Value Betting" },
      { id: "de-vig", title: "Odd Oposta (De-Vig)" },
      { id: "radar-anomalias", title: "Radar de Anomalias" },
      { id: "alerta-desvio", title: "Alerta de Desvio (Placar Exato)" },
    ],
  },
  {
    group: "Fechamento", icon: <Gauge className="w-4 h-4" />,
    items: [
      { id: "como-interpretar", title: "Como interpretar uma análise" },
      { id: "consideracoes-finais", title: "Considerações Finais" },
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
      <aside className="lg:sticky lg:top-20 lg:self-start lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto lg:pr-2">
        <div className="flex items-center gap-2 mb-3 sticky top-0 bg-background/95 backdrop-blur-sm pb-1">
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
        {/* Destaque da oferta ParcerIA — topo da página */}
        <ParcerIAHighlight />

        {/* ---------------- Começando ---------------- */}
        <Section id="visao-geral" title="Visão Geral">
          <p>Utilizar a plataforma é simples.</p>
          <p>Primeiro, você escolhe duas seleções para analisar. Elas podem fazer parte de uma partida oficial futura ou apenas representar um confronto hipotético para estudo.</p>
          <p>Depois disso, a Inteligência Artificial processa centenas de informações e gera uma análise completa da partida.</p>
          <p>Você recebe:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>probabilidades dos principais mercados;</li>
            <li>odds justas;</li>
            <li>indicadores estatísticos;</li>
            <li>análise de valor esperado (Value Betting);</li>
            <li>diversas ferramentas para interpretar melhor o confronto.</li>
          </ul>
          <p>Quando a partida for oficial e ainda não tiver acontecido, você também poderá participar da promoção &quot;ParcerIA&quot;, montando sua própria aposta dentro da plataforma.</p>
        </Section>

        <Section id="analise-independente" title="Análise Independente">
          <p>A Análise Independente permite comparar quaisquer duas seleções, mesmo que elas nunca venham a se enfrentar oficialmente.</p>
          <p>É ideal para responder perguntas como:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Quem seria favorito hoje entre Brasil e Alemanha?</li>
            <li>Como seria um Japão x Uruguai?</li>
          </ul>
          <p>Nesse modo, o sistema utiliza todas as informações disponíveis para simular o confronto e gerar as probabilidades dos mercados normalmente, como se fosse uma partida real.</p>
          <p>Como não existe uma partida oficial associada, essa modalidade serve exclusivamente para estudo e não participa de promoções nem acompanha resultados.</p>
          <p><b>Custo:</b> 1 crédito, consumido imediatamente após a geração da análise.</p>
        </Section>

        <Section id="partida-futura" title="Análise de Partida Futura">
          <p>Aqui você analisa uma partida oficial que já está marcada e ainda será disputada.</p>
          <p>O funcionamento é um pouco diferente.</p>
          <p>Ao gerar a análise, o sistema não consome imediatamente o crédito. Ele apenas o reserva até que a partida termine.</p>
          <p>Enquanto isso, você pode utilizar todos os recursos da análise e ainda montar sua aposta para participar da promoção &quot;ParcerIA&quot;.</p>
          <p>Depois do encerramento da partida, o sistema verifica automaticamente o resultado e decide se o crédito será consumido ou devolvido à sua carteira.</p>
        </Section>

        <Section id="creditos" title="Créditos">
          <p>Os créditos representam o custo do processamento realizado pela Inteligência Artificial.</p>
          <p>Cada análise exige que nossos modelos processem centenas de variáveis estatísticas, executem diversos modelos matemáticos e gerem probabilidades para dezenas de mercados.</p>
          <p>Por isso, cada nova análise utiliza créditos.</p>
          <p>Hoje, o crédito custa, no máximo, 1 real! (Ver promoções na Carteira →)</p>
          <p>Existem duas formas de utilização:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li><b>Análise Independente:</b> o crédito é consumido imediatamente.</li>
            <li><b>Partida Futura:</b> o crédito fica apenas reservado até a conclusão da promoção.</li>
          </ul>
          <p>Toda movimentação fica registrada na sua Carteira, onde você pode acompanhar créditos disponíveis, reservados e o histórico completo de utilização.</p>
        </Section>

        <Section id="promocao" title='Promoção "ParcerIA"'>
          <p>Essa promoção foi criada para tornar o uso da plataforma ainda mais interessante.</p>
          <p>Ao gerar uma análise para uma partida oficial futura, o sistema apenas reserva um crédito.</p>
          <p>Depois disso, você monta uma aposta utilizando os mercados disponíveis na própria plataforma.</p>
          <p>Quando a partida termina:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>se sua aposta estiver correta, o crédito reservado é consumido normalmente;</li>
            <li>se ela não vencer, ou não puder ser apurada, o crédito retorna integralmente para sua carteira.</li>
          </ul>
          <p>Na prática, você só utiliza o crédito quando acerta a aposta construída.</p>
          <p>Essa é uma campanha promocional da ApostaInfo. Ela não representa uma aposta ou jogo de azar, e não envolve pagamento de prêmios em dinheiro.</p>
        </Section>

        <Section id="monte-sua-aposta" title="Monte sua Aposta">
          <p>Após gerar uma análise para uma partida oficial, você pode montar sua própria aposta utilizando os mercados disponíveis.</p>
          <p>Basta escolher as seleções desejadas.</p>
          <p>Nos mercados de linha, como Over/Under, as opções aparecem organizadas em duas colunas:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Acima de</li>
            <li>Abaixo de</li>
          </ul>
          <p>À medida que você adiciona mercados, a odd combinada é atualizada automaticamente.</p>
          <p>Para manter o equilíbrio da promoção, a odd total não pode ultrapassar 2,00.</p>
          <p>Caso você não queira montar manualmente sua aposta, não há problema: a plataforma seleciona automaticamente uma combinação cuja odd fique próxima desse limite.</p>
          <p>Depois da confirmação, a aposta fica registrada e não poderá mais ser alterada.</p>
        </Section>

        {/* ---------------- Mercados ---------------- */}
        <Section id="mercado-resultado" title="Resultado (1X2)">
          <p>Este é o mercado mais tradicional do futebol.</p>
          <p>Aqui mostramos a probabilidade de cada um dos três resultados possíveis da partida:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Vitória da equipe mandante (1)</li>
            <li>Empate (X)</li>
            <li>Vitória da equipe visitante (2)</li>
          </ul>
          <p>Por exemplo:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Brasil: 61%</li>
            <li>Empate: 24%</li>
            <li>Argentina: 15%</li>
          </ul>
          <p>Isso significa que, segundo o modelo estatístico da ApostaInfo, o Brasil possui aproximadamente 61% de chance de vencer esse confronto.</p>
          <p>Essas probabilidades são utilizadas para calcular as odds justas do mercado e servem como referência para comparação com as odds oferecidas pelas casas de apostas.</p>
        </Section>

        <Section id="mercado-btts" title="Ambas Marcam (BTTS)">
          <p>O mercado Ambas Marcam (BTTS - Both Teams To Score) estima a probabilidade de que as duas seleções façam pelo menos um gol durante a partida.</p>
          <p>Exemplos:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>✅ Brasil 2 × 1 França</li>
            <li>✅ Espanha 1 × 1 Alemanha</li>
            <li>❌ Inglaterra 3 × 0 Japão</li>
            <li>❌ Portugal 2 × 0 México</li>
          </ul>
          <p>Mesmo uma equipe vencendo com facilidade, basta que o adversário não marque para que o mercado seja perdido.</p>
          <p>Esse mercado costuma ser bastante influenciado pelo equilíbrio ofensivo das equipes e pela qualidade defensiva de cada seleção.</p>
        </Section>

        <Section id="mercado-over25" title="Mais/Menos de 2,5 Gols">
          <p>Este mercado responde a uma pergunta muito simples: a partida terá muitos gols ou poucos gols?</p>
          <p>A linha mais popular é 2,5 gols.</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Over 2,5 → a partida termina com 3 gols ou mais.</li>
            <li>Under 2,5 → a partida termina com 2 gols ou menos.</li>
          </ul>
          <p>Exemplos:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>2 × 1 → Over ✅</li>
            <li>3 × 2 → Over ✅</li>
            <li>1 × 1 → Under ✅</li>
            <li>2 × 0 → Under ✅</li>
          </ul>
          <p>Além da linha de 2,5, a plataforma permite explorar diversas outras linhas, como 1,5; 3,5; 4,5 e muitas outras.</p>
        </Section>

        <Section id="mercado-placar" title="Placar Exato">
          <p>Aqui você encontra os placares mais prováveis para aquela partida segundo o modelo.</p>
          <p>Em vez de mostrar apenas um resultado, apresentamos normalmente os três cenários mais prováveis.</p>
          <p>Exemplo:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>1 × 0</li>
            <li>2 × 1</li>
            <li>1 × 1</li>
          </ul>
          <p>Isso não significa que outro placar seja impossível. Significa apenas que, entre todos os placares possíveis, esses foram os que receberam maior probabilidade pelo modelo.</p>
          <p>Quando identificamos que existe uma chance incomum de ocorrer um placar fora do padrão, também exibimos um <a className="text-primary underline" href="#alerta-desvio">Alerta de Desvio</a>, indicando que o jogo pode fugir dos cenários mais tradicionais.</p>
        </Section>

        <Section id="mercado-gols" title="Gols">
          <p>Este mercado reúne todas as previsões relacionadas à quantidade de gols.</p>
          <p>Você pode consultar probabilidades para:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>gols da equipe mandante;</li>
            <li>gols da equipe visitante;</li>
            <li>total de gols da partida;</li>
            <li>gols no primeiro tempo;</li>
            <li>gols no segundo tempo.</li>
          </ul>
          <p>Cada mercado possui diversas linhas Over/Under.</p>
          <p>Exemplo:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Brasil Over 1,5 gols</li>
            <li>Argentina Under 0,5 gol</li>
            <li>Total Over 3,5 gols</li>
          </ul>
          <p>Essas informações permitem analisar tanto o desempenho ofensivo de uma equipe quanto o comportamento esperado da partida como um todo.</p>
        </Section>

        <Section id="mercado-finalizacoes" title="Finalizações">
          <p>Finalizações representam todas as tentativas de gol realizadas durante a partida.</p>
          <p>São contabilizados:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>chutes no gol;</li>
            <li>chutes para fora;</li>
            <li>cabeçadas;</li>
            <li>bolas na trave;</li>
            <li>finalizações bloqueadas pela defesa.</li>
          </ul>
          <p>Exemplo: uma equipe pode terminar a partida com 18 finalizações, apenas 7 delas no alvo.</p>
          <p>Isso mostra que volume ofensivo não significa necessariamente eficiência.</p>
          <p>Esse mercado costuma refletir o ritmo ofensivo esperado de cada seleção.</p>
        </Section>

        <Section id="mercado-finalizacoes-gol" title="Finalizações a Gol">
          <p>Diferentemente do mercado anterior, aqui consideramos apenas os chutes que realmente foram na direção da meta.</p>
          <p>Ou seja, aqueles que exigiriam uma defesa do goleiro ou terminariam em gol caso ninguém interviesse.</p>
          <p>Exemplo: 20 finalizações, das quais 8 no alvo.</p>
          <p>Esse mercado costuma apresentar uma relação mais forte com a criação de chances claras e com a probabilidade de gols.</p>
        </Section>

        <Section id="mercado-escanteios" title="Escanteios">
          <p>Aqui estimamos quantos escanteios cada seleção deverá cobrar ao longo da partida.</p>
          <p>Também calculamos o total esperado do jogo.</p>
          <p>Exemplos:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Brasil Over 5,5 escanteios</li>
            <li>Total Over 9,5 escanteios</li>
          </ul>
          <p>Escanteios normalmente estão relacionados ao volume ofensivo, à pressão exercida pelas equipes e ao estilo de jogo de cada seleção.</p>
          <p>Equipes que atacam bastante costumam gerar mais escanteios ao longo da partida.</p>
        </Section>

        <Section id="mercado-cartoes" title="Cartões">
          <p>Este mercado estima a quantidade de cartões amarelos + vermelhos esperados durante o jogo.</p>
          <p>Você pode consultar probabilidades para:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>cartões de cada equipe;</li>
            <li>total da partida;</li>
            <li>primeiro tempo;</li>
            <li>segundo tempo.</li>
          </ul>
          <p>Além do histórico disciplinar das seleções, fatores como equilíbrio da partida, importância do confronto e intensidade esperada também influenciam essa previsão.</p>
          <p>Jogos eliminatórios, por exemplo, costumam apresentar comportamentos diferentes de amistosos.</p>
        </Section>

        <Section id="mercado-odds-justas" title="Odds Justas dos Mercados">
          <p>Todos os mercados apresentados na plataforma possuem uma odd justa correspondente à probabilidade calculada pelo modelo.</p>
          <p>Essas odds representam quanto um evento deveria pagar caso não existisse margem de lucro para a casa de apostas.</p>
          <p>Por exemplo: se nosso modelo estima que determinado evento possui 50% de chance de acontecer, sua odd justa será aproximadamente 2,00.</p>
          <p>Se uma casa oferece uma odd significativamente superior à odd justa estimada pela plataforma, pode existir uma oportunidade de valor — assunto que exploramos na ferramenta <a className="text-primary underline" href="#value-betting">Value Betting</a>.</p>
        </Section>

        {/* ---------------- Como os modelos funcionam ---------------- */}
        <Section id="modelo-dixon-coles" title="Dixon-Coles + Binomial Negativa (Resultado e Gols)">
          <p>Este é o principal modelo da ApostaInfo e o responsável por calcular praticamente todos os mercados relacionados aos gols da partida.</p>
          <p>Antes de estimar qualquer probabilidade, a Inteligência Artificial avalia centenas de informações sobre as duas seleções, como:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>força das equipes (Elo Rating);</li>
            <li>desempenho recente;</li>
            <li>desempenho ofensivo e defensivo;</li>
            <li>qualidade dos adversários enfrentados;</li>
            <li>mando de campo;</li>
            <li>tempo de descanso;</li>
            <li>momento da equipe na competição;</li>
            <li>histórico entre as seleções;</li>
            <li>e muitas outras variáveis.</li>
          </ul>
          <p>A partir dessas informações, o modelo estima quantos gols cada equipe tende a marcar e combina todos os placares possíveis para calcular as probabilidades de vitória, empate, derrota, gols, placar exato e diversos outros mercados.</p>
          <p>Como todos esses mercados são derivados do mesmo modelo matemático, eles permanecem coerentes entre si.</p>
          <p>Por exemplo, se o sistema estima uma alta probabilidade de muitos gols, essa característica naturalmente será refletida também nos mercados de Over, Ambas Marcam e Placar Exato.</p>
        </Section>

        <Section id="modelo-cascata" title="Modelagem em Cascata">
          <p>Uma partida de futebol é formada por eventos que acontecem em sequência.</p>
          <p>Normalmente: mais ataques → mais finalizações → mais escanteios → maior chance de cartões.</p>
          <p>Em vez de prever cada mercado de forma totalmente independente, a ApostaInfo considera essa relação natural entre os eventos do jogo.</p>
          <p>Isso faz com que as previsões fiquem mais consistentes.</p>
          <p>Por exemplo: se o modelo identifica que uma equipe deve dominar a partida e finalizar bastante, é esperado que ela também produza mais escanteios do que normalmente produziria.</p>
          <p>Essa dependência entre os mercados torna a análise muito mais próxima do comportamento real de uma partida.</p>
        </Section>

        <Section id="modelo-cartoes" title="Modelo de Cartões">
          <p>Cartões costumam ser um dos mercados mais difíceis de prever.</p>
          <p>Uma partida pode terminar com apenas um cartão ou ultrapassar dez advertências dependendo do contexto do jogo.</p>
          <p>Por isso utilizamos um modelo estatístico específico para esse tipo de evento, capaz de representar melhor partidas extremamente tranquilas e jogos muito disputados.</p>
          <p>Além do histórico disciplinar das equipes, o sistema considera fatores como:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>importância da partida;</li>
            <li>fase da competição;</li>
            <li>equilíbrio esperado do confronto;</li>
            <li>estilo de jogo das seleções.</li>
          </ul>
          <p>Tudo isso contribui para uma estimativa mais realista do comportamento disciplinar da partida.</p>
        </Section>

        <Section id="modelo-calibracao" title="Calibração das Linhas Over/Under">
          <p>Depois que os modelos calculam todas as probabilidades, elas passam por uma etapa adicional chamada calibração.</p>
          <p>O objetivo é garantir que os números apresentados sejam realmente confiáveis.</p>
          <p>Imagine que o sistema diga que determinado evento possui 70% de chance de acontecer. Ao analisar milhares de partidas semelhantes, esperamos que esse evento realmente ocorra aproximadamente 70% das vezes.</p>
          <p>Essa etapa reduz distorções naturais dos modelos estatísticos e torna as odds justas muito mais consistentes.</p>
          <p>Em outras palavras, ela ajuda a fazer com que as probabilidades exibidas representem melhor a realidade.</p>
        </Section>

        <Section id="metrica-log-loss" title="Log-Loss">
          <p>Nem sempre um modelo é melhor apenas porque &quot;acerta&quot; mais resultados.</p>
          <p>O mais importante é saber o quanto ele estava confiante em cada previsão. É exatamente isso que mede o Log-Loss.</p>
          <p>Imagine dois modelos:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li><b>Modelo A:</b> Brasil vence com 55% de chance.</li>
            <li><b>Modelo B:</b> Brasil vence com 98% de chance.</li>
          </ul>
          <p>Se o Brasil perder, qual dos dois errou mais? Claramente o segundo.</p>
          <p>O Log-Loss penaliza justamente esse excesso de confiança. Por isso utilizamos essa métrica como uma das principais referências durante o desenvolvimento dos modelos.</p>
          <p>Nosso objetivo não é apenas acertar resultados, mas atribuir probabilidades realistas a cada evento.</p>
        </Section>

        <Section id="metrica-ece" title="Calibração (ECE)">
          <p>Outro indicador importante é a calibração das probabilidades.</p>
          <p>Ela responde a uma pergunta simples: quando o modelo informa 80% de chance, esse evento realmente acontece perto de 80% das vezes?</p>
          <p>Se a resposta for sim, significa que o modelo está bem calibrado.</p>
          <p>Quanto menor o ECE (Expected Calibration Error), maior a confiança que podemos ter nas probabilidades apresentadas.</p>
          <p>Esse indicador é constantemente monitorado para garantir que nossas odds justas permaneçam consistentes ao longo do tempo.</p>
        </Section>

        <Section id="modelo-varios" title="Por que utilizamos vários modelos?">
          <p>Cada mercado possui características diferentes.</p>
          <p>A quantidade de gols de uma partida não se comporta da mesma forma que o número de escanteios ou cartões.</p>
          <p>Por isso não utilizamos um único algoritmo para tudo. Cada mercado é modelado utilizando a abordagem estatística mais adequada para aquele tipo de evento.</p>
          <p>Isso permite que cada previsão seja construída levando em consideração as características específicas daquele mercado, resultando em análises mais precisas e coerentes.</p>
        </Section>

        <Section id="modelo-aprendizado" title="Inteligência Artificial e Aprendizado Contínuo">
          <p>Os modelos da ApostaInfo são constantemente reavaliados.</p>
          <p>Novos jogos, novas estatísticas e novas variáveis são incorporados periodicamente para que as previsões reflitam o momento atual das seleções.</p>
          <p>Além do histórico de longo prazo, nossos modelos também dão grande importância ao desempenho recente das equipes, identificando tendências, mudanças de comportamento e evolução ao longo da competição.</p>
          <p>Isso significa que uma seleção não é avaliada apenas pelo que fez anos atrás, mas principalmente pela forma como vem jogando atualmente.</p>
        </Section>

        {/* ---------------- Ferramentas e Recursos ---------------- */}
        <Section id="metrica-faixa-odd" title="Faixa de Odd Justa">
          <p>A ApostaInfo não exibe apenas uma odd justa, mas uma faixa de referência.</p>
          <p>Isso acontece porque toda previsão estatística possui um pequeno grau de incerteza.</p>
          <p>Em vez de dizer que a odd justa é exatamente 2,05, mostramos um intervalo onde ela provavelmente se encontra.</p>
          <p>Essa faixa ajuda você a comparar as odds oferecidas pelas casas de apostas e avaliar se existe valor na aposta.</p>
          <p>Por exemplo:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Odd da casa: 2,40</li>
            <li>Faixa de odd justa da ApostaInfo: 1,95 a 2,10</li>
          </ul>
          <p>Nesse caso, a casa está pagando acima do que nosso modelo considera justo, o que pode indicar uma oportunidade interessante.</p>
          <p><b>Importante:</b> a odd justa não inclui a margem de lucro da casa e não representa uma recomendação de aposta.</p>
        </Section>

        <Section id="metrica-confiabilidade" title="Confiabilidade dos Dados">
          <p>Nem todas as seleções possuem o mesmo volume de informações disponíveis.</p>
          <p>Algumas disputam competições frequentemente e possuem estatísticas extremamente detalhadas. Outras jogam poucas partidas ou têm cobertura estatística limitada.</p>
          <p>Por isso exibimos um selo de confiabilidade dos dados utilizados na análise.</p>
          <ul className="list-disc pl-5 space-y-1">
            <li><b>Alta:</b> grande quantidade de estatísticas detalhadas e histórico consistente. As previsões tendem a ser mais confiáveis.</li>
            <li><b>Média:</b> boa quantidade de dados, mas com algumas limitações. Ainda é possível gerar análises consistentes.</li>
            <li><b>Baixa:</b> poucos dados disponíveis. As probabilidades continuam sendo calculadas normalmente, mas apresentam um nível maior de incerteza.</li>
          </ul>
          <p>Esse indicador não mede a qualidade da seleção, e sim a qualidade da informação disponível para analisá-la.</p>
        </Section>

        <Section id="explorador-de-linha" title="Explorador de Linha">
          <p>Nem sempre a linha mais popular é a que oferece o melhor equilíbrio entre risco e retorno.</p>
          <p>O Explorador de Linha permite navegar rapidamente por todas as linhas disponíveis para um mesmo mercado.</p>
          <p>Por exemplo, em vez de analisar apenas Over 2,5 gols, você pode visualizar instantaneamente:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Over 1,5</li>
            <li>Over 2,5</li>
            <li>Over 3,5</li>
            <li>Over 4,5</li>
          </ul>
          <p>com suas respectivas probabilidades e odds justas.</p>
          <p>O mesmo vale para mercados como: escanteios; cartões; finalizações; finalizações a gol.</p>
          <p>É uma excelente ferramenta para encontrar a linha que mais se adapta à sua estratégia.</p>
        </Section>

        <Section id="value-betting" title="Value Betting — Identificação de Valor">
          <p>Nem sempre apostar no evento mais provável é a melhor decisão.</p>
          <p>O conceito de Value Betting busca identificar situações em que a odd oferecida pela casa está acima daquela que nosso modelo considera justa.</p>
          <p>Imagine o seguinte exemplo:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Nossa estimativa: 60% de chance.</li>
            <li>Odd justa: 1,67</li>
            <li>A casa oferece: 2,05</li>
          </ul>
          <p>Mesmo que essa aposta possa perder hoje, ela possui valor esperado positivo no longo prazo, pois está pagando acima do que deveria segundo nosso modelo.</p>
          <p>A plataforma calcula automaticamente esse diferencial e apresenta indicadores como:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Valor Esperado (EV);</li>
            <li>ROI estimado;</li>
            <li>vantagem sobre a odd da casa.</li>
          </ul>
          <p>Essas informações servem como ferramenta de apoio à decisão e não representam garantia de lucro.</p>
        </Section>

        <Section id="de-vig" title="Odd Oposta (De-Vig)">
          <p>As odds das casas de apostas já incluem uma margem de lucro para a própria casa.</p>
          <p>Por isso, a probabilidade implícita obtida diretamente pelas odds costuma estar distorcida.</p>
          <p>Quando você informa também a odd do lado oposto do mercado, a ApostaInfo remove essa margem automaticamente.</p>
          <p>Isso permite estimar qual é a probabilidade &quot;real&quot; que a casa provavelmente atribuiu ao evento.</p>
          <p>Na prática, você passa a comparar:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>a probabilidade estimada pelo mercado;</li>
            <li>a probabilidade calculada pela ApostaInfo.</li>
          </ul>
          <p>Essa comparação é muito mais justa e ajuda a identificar possíveis oportunidades de valor.</p>
          <p><b>Exemplo prático:</b> imagine que uma casa de apostas oferece as seguintes odds para o mercado Mais de 2,5 gols:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Over 2,5: 1,80</li>
            <li>Under 2,5: 2,00</li>
          </ul>
          <p>Se você olhar apenas para a odd 1,80, ela parece indicar uma probabilidade de 55,6% (1 ÷ 1,80). Mas essa probabilidade ainda inclui a margem de lucro da casa.</p>
          <p>Ao informar também a odd do lado oposto (2,00), a ApostaInfo remove essa margem (de-vig) e estima que a probabilidade real atribuída pela casa ao Over 2,5 é de aproximadamente 52,6%.</p>
          <p>Agora compare:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>Probabilidade da casa (sem margem): 52,6%</li>
            <li>Probabilidade da ApostaInfo: 59,8%</li>
          </ul>
          <p>Essa diferença indica que o nosso modelo considera esse evento mais provável do que o mercado considera. Se a odd oferecida continuar em 1,80, pode existir uma oportunidade de Value Betting, pois a casa está pagando acima da odd justa estimada pelo nosso modelo.</p>
        </Section>

        <Section id="radar-anomalias" title="Radar de Anomalias">
          <p>Nem sempre uma seleção está jogando da forma que costuma jogar.</p>
          <p>O Radar de Anomalias identifica justamente essas mudanças recentes de comportamento.</p>
          <p>Por exemplo, ele pode mostrar que uma equipe:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>está finalizando muito mais do que sua média histórica;</li>
            <li>sofreu uma queda brusca na produção ofensiva;</li>
            <li>passou a conceder muitos escanteios;</li>
            <li>vem recebendo uma quantidade incomum de cartões;</li>
            <li>apresenta um desempenho muito diferente do esperado.</li>
          </ul>
          <p>Esses desvios ajudam a entender quando uma equipe atravessa um momento atípico e podem explicar por que determinadas probabilidades ficaram diferentes do habitual.</p>
        </Section>

        <Section id="alerta-desvio" title="Alerta de Desvio (Placar Exato)">
          <p>Algumas partidas fogem completamente do comportamento mais comum observado no futebol.</p>
          <p>Quando isso acontece, a plataforma exibe um Alerta de Desvio.</p>
          <p>Esse aviso indica que existe uma probabilidade maior do que o normal de ocorrer um placar fora dos resultados mais tradicionais.</p>
          <p>Isso pode acontecer, por exemplo, quando:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>uma seleção é muito superior à outra;</li>
            <li>o modelo prevê uma partida com muitos gols;</li>
            <li>existe grande desequilíbrio entre ataque e defesa;</li>
            <li>há maior probabilidade de placares elásticos.</li>
          </ul>
          <p>O alerta não informa qual será o placar final, mas ajuda a interpretar melhor os resultados apresentados no mercado de Placar Exato.</p>
        </Section>

        {/* ---------------- Fechamento ---------------- */}
        <Section id="como-interpretar" title="Como interpretar uma análise">
          <p>Uma análise completa não deve ser vista como um único número ou uma única previsão.</p>
          <p>O ideal é observar o conjunto de informações apresentado pela plataforma.</p>
          <p>Por exemplo:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>O favoritismo apontado no mercado Resultado (1X2) está coerente com a expectativa de gols?</li>
            <li>A previsão de escanteios faz sentido considerando o estilo ofensivo das equipes?</li>
            <li>A odd oferecida pela casa está acima da odd justa calculada pela plataforma?</li>
            <li>Existe algum desvio recente no comportamento de uma das seleções?</li>
            <li>O nível de confiabilidade dos dados é alto?</li>
          </ul>
          <p>Quanto mais mercados apontarem para a mesma direção, maior tende a ser a consistência da análise.</p>
          <p>A ApostaInfo foi desenvolvida para fornecer esse contexto completo, permitindo que você tome decisões mais bem fundamentadas.</p>
        </Section>

        <Section id="consideracoes-finais" title="Considerações Finais">
          <p>O objetivo da ApostaInfo não é prever o futuro com certeza absoluta, mas transformar grandes volumes de dados em informações claras, objetivas e úteis para a análise de partidas entre seleções.</p>
          <p>Nossos modelos utilizam Inteligência Artificial, estatística avançada e centenas de variáveis para estimar probabilidades de diversos mercados. Ainda assim, o futebol continua sendo um esporte cheio de imprevisibilidades.</p>
          <p>Por isso, utilize as análises como uma ferramenta de apoio à decisão, compare-as com sua própria leitura da partida e, sempre que possível, avalie as odds oferecidas pelo mercado antes de tomar qualquer decisão.</p>
        </Section>

        <p className="text-xs text-muted-foreground pt-2">
          As odds justas são referência analítica, sem margem de casa, e não constituem recomendação de aposta. Jogue com responsabilidade.
        </p>
      </div>
    </div>
  );
}
