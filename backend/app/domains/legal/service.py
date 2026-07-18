"""Documentos legais versionados + registro de aceite (data/hora + IP).

Cada tipo de documento tem uma versão vigente (is_current). Quando um documento é
republicado, cria-se uma NOVA versão vigente e a anterior deixa de ser vigente — o
sistema passa a exigir NOVO aceite (pending_for_user detecta quem ainda não aceitou a
versão vigente).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.enums import LegalDocumentType
from app.domains.legal import schemas
from app.domains.legal.models import LegalDocument, UserDocumentAcceptance

# Conteúdo inicial (v1) — BASE SÓLIDA PARA REVISÃO JURÍDICA/CONTÁBIL. Razão social, CNPJ,
# endereço e e-mail de suporte já preenchidos (SaferCode Softwares). Após alterar o texto
# aqui, rode `python -m scripts.republish_legal_docs` para publicar nova versão vigente
# (isso força novo aceite de todos os usuários).
_DEFAULTS: dict[LegalDocumentType, tuple[str, str]] = {
    LegalDocumentType.terms: (
        "Termos de Uso",
        "# Termos de Uso\n\n"
        "Última atualização: 18/07/2026. Estes Termos de Uso regem o acesso e uso da plataforma "
        "ApostaInfo (apostainfo.com.br), operada por SaferCode Softwares, CNPJ 66.097.260/0001-35, com sede em "
        "Rua Profa. Ângela Pinto, 97, Torre, Recife-PE (\"ApostaInfo\", \"nós\"). Ao criar uma conta ou usar o site, você (\"usuário\") "
        "concorda integralmente com estes termos.\n\n"
        "**Aviso importante:** a ApostaInfo é exclusivamente uma plataforma de análise estatística "
        "baseada em Inteligência Artificial. A contratação do serviço remunera apenas a geração "
        "das análises solicitadas pelo usuário, não constituindo participação em apostas "
        "esportivas, jogos de azar, investimento financeiro ou promessa de retorno econômico.\n\n"
        "## 1. O que é a ApostaInfo\n\n"
        "1.1 A ApostaInfo é uma plataforma de análise estatística e previsão probabilística de "
        "partidas de futebol, baseada em modelos matemáticos (Dixon-Coles, distribuições de "
        "probabilidade e outros). O serviço prestado é a geração de análises — não é casa de "
        "apostas, corretora de valores ou consultoria de investimentos.\n\n"
        "1.2 As projeções apresentadas são estimativas estatísticas sobre eventos esportivos "
        "reais, sujeitos a incerteza e volatilidade inerentes. Nenhuma análise garante resultado, "
        "lucro ou acerto. O usuário é o único responsável por decisões tomadas com base nas "
        "análises.\n\n"
        "1.3 A ApostaInfo não é afiliada a nenhuma casa de apostas, liga esportiva ou federação, "
        "e não intermedia, processa ou garante apostas em plataformas de terceiros.\n\n"
        "1.4 A plataforma não incentiva ou recomenda a realização de apostas em qualquer operador "
        "nacional ou internacional. As análises possuem finalidade exclusivamente estatística e "
        "informativa.\n\n"
        "## 2. Cadastro e elegibilidade\n\n"
        "2.1 O uso da plataforma é restrito a maiores de 18 anos, com capacidade civil plena. "
        "Podemos solicitar comprovação documental da idade quando necessário.\n\n"
        "2.2 O cadastro exige nome completo, e-mail, CPF e telefone verdadeiros. É proibido criar "
        "contas com dados de terceiros ou múltiplas contas para a mesma pessoa (ex.: para acumular "
        "bônus de indicação ou burlar limites promocionais).\n\n"
        "2.3 O usuário é responsável por manter a confidencialidade de sua senha e por toda "
        "atividade realizada em sua conta.\n\n"
        "## 3. Créditos e pagamentos\n\n"
        "3.1 O acesso às análises é remunerado por créditos, cuja compra, consumo, reserva e "
        "estorno são regidos pela Política de Créditos, parte integrante destes Termos.\n\n"
        "3.2 Pagamentos são processados por gateway de pagamento terceirizado (atualmente Mercado "
        "Pago), via PIX ou cartão. A ApostaInfo não armazena dados de cartão de crédito.\n\n"
        "## 4. Uso aceitável\n\n"
        "4.1 É proibido: (a) compartilhar, revender, copiar ou redistribuir análises geradas por "
        "sua conta a terceiros, por qualquer meio (captura de tela, impressão, reenvio); (b) "
        "utilizar robôs, scraping ou automação para extrair dados da plataforma; (c) tentar burlar "
        "o sistema de créditos, cupons, indicações ou o Programa de Parceiros; (d) utilizar a "
        "plataforma para fins ilícitos.\n\n"
        "4.2 O descumprimento pode resultar em advertência, estorno de créditos indevidamente "
        "obtidos, suspensão ou cancelamento da conta, sem prejuízo de outras medidas cabíveis.\n\n"
        "4.3 São exemplos de fraude sujeitos às medidas acima: autoindicação; criação de contas "
        "falsas; utilização de CPFs de terceiros; e uso automatizado (por script, robô ou "
        "ferramenta similar) de cupons promocionais.\n\n"
        "## 5. Propriedade intelectual\n\n"
        "5.1 Modelos, algoritmos, textos, marca, layout e demais conteúdos da plataforma são de "
        "propriedade da ApostaInfo ou de seus licenciantes, protegidos por direito autoral. O uso "
        "da plataforma não transfere nenhum direito de propriedade intelectual ao usuário.\n\n"
        "## 6. Limitação de responsabilidade\n\n"
        "6.1 Na máxima extensão permitida em lei, a ApostaInfo não se responsabiliza por perdas "
        "financeiras, diretas ou indiretas, decorrentes de decisões tomadas com base nas análises, "
        "indisponibilidade temporária do serviço, ou por instabilidade de fontes de dados "
        "esportivos de terceiros (ex.: atraso ou erro em resultado oficial de partida).\n\n"
        "6.2 A responsabilidade da ApostaInfo perante o usuário, quando aplicável, está limitada ao "
        "valor efetivamente pago pelo usuário nos 3 meses anteriores ao evento gerador.\n\n"
        "6.3 Nenhuma funcionalidade da plataforma constitui recomendação personalizada, "
        "consultoria financeira, consultoria esportiva ou sugestão individualizada de aposta.\n\n"
        "6.4 Não garantimos disponibilidade contínua da plataforma, podendo ocorrer interrupções "
        "programadas ou emergenciais.\n\n"
        "## 7. Cancelamento e direito de arrependimento\n\n"
        "7.1 O usuário pode encerrar sua conta a qualquer momento pelo e-mail de suporte. Nos "
        "termos do art. 49 do Código de Defesa do Consumidor, compras de créditos realizadas fora "
        "do estabelecimento comercial podem ser canceladas em até 7 dias, desde que os créditos "
        "ainda não tenham sido consumidos (ver Política de Créditos).\n\n"
        "## 8. Alterações destes termos\n\n"
        "8.1 Estes termos podem ser atualizados a qualquer momento. Alterações relevantes geram "
        "nova versão vigente e exigem novo aceite do usuário antes de novas compras ou análises.\n\n"
        "8.2 Nenhuma alteração produzirá efeitos retroativos sobre compras já concluídas ou "
        "análises já geradas.\n\n"
        "## 9. Legislação aplicável\n\n"
        "9.1 Este contrato é regido pelas leis brasileiras, observado o foro do domicílio do "
        "consumidor nos termos do Código de Defesa do Consumidor.\n\n"
        "## 10. Contato\n\n"
        "Dúvidas, suporte ou solicitações: contato@safercode.com.br.",
    ),
    LegalDocumentType.privacy: (
        "Política de Privacidade",
        "# Política de Privacidade\n\n"
        "Última atualização: 18/07/2026. Esta Política descreve como SaferCode Softwares (CNPJ 66.097.260/0001-35) "
        "coleta, usa, armazena e protege os dados pessoais dos usuários da ApostaInfo, em "
        "conformidade com a Lei Geral de Proteção de Dados (Lei nº 13.709/2018 — LGPD).\n\n"
        "## 1. Dados que coletamos\n\n"
        "1.1 Dados de cadastro: nome completo, e-mail, CPF, telefone.\n\n"
        "1.2 Dados de pagamento: histórico de compras, valor, método (PIX/cartão) e status — os "
        "dados sensíveis do cartão são processados diretamente pelo gateway de pagamento (Mercado "
        "Pago) e nunca chegam aos nossos servidores.\n\n"
        "1.3 Dados de uso: análises geradas, participações em campanhas promocionais, cupons "
        "utilizados, indicações, endereço IP, data/hora de acesso, tipo de dispositivo e "
        "navegador.\n\n"
        "1.4 Cookies e tecnologias similares, para manter sessão de login, proteger sua conta e "
        "medir uso da plataforma (ver seção 7).\n\n"
        "## 2. Para que usamos seus dados\n\n"
        "2.1 Prestar o serviço (gerar análises, processar compras, liquidar campanhas "
        "promocionais, emitir nota fiscal); autenticar e proteger sua conta; cumprir obrigações "
        "legais e fiscais; prevenir fraude e uso indevido (ex.: contas duplicadas, abuso de "
        "cupons); e, mediante consentimento específico, enviar comunicações de marketing.\n\n"
        "## 3. Base legal (art. 7º da LGPD)\n\n"
        "3.1 Execução de contrato (prestação do serviço), cumprimento de obrigação legal/regulatória "
        "(emissão fiscal, guarda de registros financeiros), legítimo interesse (segurança e "
        "prevenção a fraude) e consentimento (comunicações de marketing, quando aplicável).\n\n"
        "## 4. Com quem compartilhamos\n\n"
        "4.1 Processador de pagamentos (Mercado Pago), para viabilizar cobrança e liquidação. "
        "4.2 Provedores de infraestrutura (hospedagem do banco de dados, backend e frontend) e "
        "de envio de e-mail transacional, estritamente para operar a plataforma. "
        "4.3 Autoridades públicas, quando exigido por lei ou ordem judicial. "
        "4.4 Emissor de nota fiscal eletrônica, para cumprir a obrigação fiscal de cada compra. "
        "Não vendemos dados pessoais a terceiros para fins de publicidade.\n\n"
        "## 5. Por quanto tempo guardamos\n\n"
        "5.1 Dados cadastrais e financeiros são mantidos enquanto a conta estiver ativa e pelo "
        "prazo exigido pela legislação fiscal e civil aplicável (em geral 5 anos após o último "
        "registro). Dados de navegação/analytics são mantidos por prazo menor, conforme "
        "necessidade operacional.\n\n"
        "## 6. Uso de Inteligência Artificial\n\n"
        "6.1 As informações fornecidas pelo usuário e os dados estatísticos processados pela "
        "plataforma poderão ser utilizados para geração das análises solicitadas e para "
        "aprimoramento dos modelos estatísticos e algoritmos utilizados pela ApostaInfo, sempre "
        "observando a legislação aplicável sobre proteção de dados pessoais.\n\n"
        "## 7. Cookies\n\n"
        "7.1 Usamos: (a) cookies de autenticação, para manter sua sessão de login; (b) cookies de "
        "segurança e antifraude, para proteger sua conta e prevenir uso indevido da plataforma; e "
        "(c) cookies analíticos, para medir uso da plataforma. Você pode gerenciar cookies nas "
        "configurações do seu navegador; desativar cookies essenciais (autenticação/segurança) "
        "pode impedir o funcionamento do login.\n\n"
        "## 8. Seus direitos (art. 18 da LGPD)\n\n"
        "8.1 Você pode solicitar, a qualquer momento: confirmação do tratamento, acesso aos dados, "
        "correção de dados incompletos ou desatualizados, anonimização/eliminação de dados "
        "desnecessários, portabilidade, informação sobre compartilhamento, e revogação do "
        "consentimento (quando esta for a base legal). Solicitações podem ser feitas pelo canal "
        "indicado na seção 10.\n\n"
        "## 9. Segurança\n\n"
        "9.1 Adotamos medidas técnicas e organizacionais razoáveis para proteger seus dados "
        "(criptografia em trânsito, controle de acesso, autenticação por token). Nenhum sistema é "
        "100% imune a incidentes; em caso de incidente de segurança relevante, os usuários e a "
        "Autoridade Nacional de Proteção de Dados serão notificados conforme exigido em lei.\n\n"
        "## 10. Encarregado de dados (DPO) e contato\n\n"
        "10.1 Para exercer seus direitos ou tirar dúvidas sobre esta Política, entre em contato "
        "pelo e-mail privacidade@apostainfo.com.br.\n\n"
        "## 11. Alterações\n\n"
        "11.1 Esta Política pode ser atualizada; alterações relevantes exigem novo aceite do "
        "usuário.",
    ),
    LegalDocumentType.lgpd: (
        "Consentimento LGPD",
        "# Consentimento para Tratamento de Dados Pessoais (LGPD)\n\n"
        "Nos termos da Lei nº 13.709/2018 (LGPD), ao aceitar este documento você consente, de "
        "forma livre, informada e inequívoca, com o tratamento dos seus dados pessoais pela "
        "ApostaInfo para as finalidades abaixo, complementares à Política de Privacidade.\n\n"
        "## 1. Finalidades do consentimento\n\n"
        "1.1 Criação e manutenção da sua conta de usuário.\n\n"
        "1.2 Processamento de compras de créditos e emissão da respectiva nota fiscal (nome, CPF "
        "e, quando aplicável, endereço).\n\n"
        "1.3 Operação do programa de indicação entre usuários e do Programa de Parceiros, "
        "incluindo identificação de quem indicou/foi indicado para fins de crédito de bônus ou "
        "comissão.\n\n"
        "1.4 Envio de comunicações operacionais (confirmação de compra, status de pagamento, "
        "resultado de campanhas promocionais) — estas não dependem de consentimento por serem "
        "necessárias à execução do serviço.\n\n"
        "1.5 Envio de comunicações de marketing (novidades, promoções, cupons) — apenas mediante "
        "este consentimento específico, podendo ser revogado a qualquer momento sem prejuízo ao "
        "uso da plataforma.\n\n"
        "## 2. Dados abrangidos\n\n"
        "2.1 Nome completo, e-mail, CPF, telefone e histórico de uso/compras descritos na Política "
        "de Privacidade.\n\n"
        "## 3. Revogação\n\n"
        "3.1 Você pode revogar este consentimento a qualquer momento, o que impede o envio de "
        "comunicações de marketing, mas não elimina dados cuja manutenção seja exigida por "
        "obrigação legal (ex.: registros fiscais).\n\n"
        "## 4. Como exercer seus direitos\n\n"
        "4.1 Solicitações de acesso, correção, portabilidade ou eliminação de dados, bem como a "
        "revogação deste consentimento, devem ser feitas pelo e-mail privacidade@apostainfo.com.br, "
        "conforme detalhado na Política de Privacidade.",
    ),
    LegalDocumentType.credits_policy: (
        "Política de Créditos",
        "# Política de Créditos\n\n"
        "## 1. O que é o crédito\n\n"
        "1.1 O crédito é a unidade que remunera o uso da Inteligência Artificial da ApostaInfo "
        "para gerar uma análise. Cada crédito equivale a R$ 1,00 (um real). Créditos não são "
        "moeda, título de crédito, criptoativo ou instrumento financeiro, não rendem juros e não "
        "podem ser convertidos em dinheiro, sacados ou transferidos entre contas, exceto pelo "
        "programa de indicação descrito na seção 6. Créditos representam exclusivamente uma "
        "licença limitada de utilização das funcionalidades da plataforma.\n\n"
        "## 2. Como se compra crédito\n\n"
        "2.1 Créditos são vendidos em pacotes pré-definidos, exibidos na Carteira, com preço em "
        "reais e, quando aplicável, créditos bônus promocionais. O pagamento é processado via "
        "Mercado Pago (PIX ou cartão) e os créditos são disponibilizados após a confirmação do "
        "pagamento pelo provedor.\n\n"
        "2.2 Cada compra confirmada gera nota fiscal de serviço, emitida em nome do CPF informado "
        "no cadastro.\n\n"
        "## 3. Como o crédito é usado\n\n"
        "3.1 Análise independente: 1 crédito é consumido imediatamente ao gerar a análise.\n\n"
        "3.2 Análise de partida futura agendada (elegível à promoção \"ParcerIA\"): 1 crédito é "
        "reservado (fica indisponível para novo uso, mas não é debitado). Após o término oficial "
        "da partida, o crédito é consumido ou estornado conforme o Regulamento da Promoção "
        "\"ParcerIA\".\n\n"
        "## 4. Estorno e cancelamento\n\n"
        "4.1 Créditos ainda não consumidos podem ser estornados em dinheiro em até 7 dias corridos "
        "da compra, nos termos do direito de arrependimento do art. 49 do CDC, desde que nenhum "
        "crédito do pacote tenha sido utilizado. Caso qualquer crédito do pacote já tenha sido "
        "consumido, o usuário reconhece que houve início da execução do serviço contratado. Após "
        "o uso de qualquer crédito do pacote, ou decorrido esse prazo, a compra é considerada "
        "consumida e não é reembolsável, ressalvado erro comprovado de cobrança ou defeito do "
        "serviço.\n\n"
        "4.2 Créditos reservados para partidas futuras são estornados automaticamente para a "
        "carteira em caso de cancelamento oficial da partida, adiamento sem nova data em prazo "
        "razoável, ou indisponibilidade de dados oficiais do resultado.\n\n"
        "## 5. Cupons e bônus\n\n"
        "5.1 Cupons promocionais concedem desconto no preço ou créditos bônus adicionais, "
        "conforme regras próprias de cada campanha (validade, pacotes elegíveis, limite de uso por "
        "conta). Cupons não têm valor de face em dinheiro, não são cumulativos entre si salvo "
        "indicação expressa, e podem ser encerrados ou alterados a qualquer momento sem aviso "
        "prévio para cupons ainda não utilizados.\n\n"
        "5.2 Créditos bônus (de cupom, campanha ou indicação) seguem as mesmas regras de uso e "
        "consumo dos créditos comprados, mas não são elegíveis a estorno em dinheiro.\n\n"
        "## 6. Programa de indicação entre usuários\n\n"
        "6.1 Ao indicar outro usuário com seu código, ambos podem receber créditos bônus conforme "
        "as regras vigentes exibidas na Carteira. Esse benefício é independente do Programa de "
        "Parceiros (comissão comercial em dinheiro a parceiros — ver documento próprio) e não "
        "pode ser acumulado de forma fraudulenta, incluindo, exemplificativamente: autoindicação; "
        "criação de contas falsas; utilização de CPFs de terceiros; e uso automatizado de "
        "cupons.\n\n"
        "## 7. Validade\n\n"
        "7.1 Créditos disponíveis não possuem prazo de expiração enquanto a conta estiver ativa, "
        "salvo aviso prévio em contrário publicado nesta política com pelo menos 30 dias de "
        "antecedência.\n\n"
        "## 8. Alteração de preços\n\n"
        "8.1 Os preços dos pacotes podem ser alterados a qualquer momento; a alteração não afeta "
        "créditos já comprados, apenas novas compras.",
    ),
    LegalDocumentType.promo_regulation: (
        "Regulamento da Promoção \"ParcerIA\"",
        "# Regulamento da Promoção \"ParcerIA\"\n\n"
        "## 1. O que é a ParcerIA\n\n"
        "1.1 \"ParcerIA\" é uma campanha comercial de estorno condicional de créditos, aplicável "
        "apenas a análises de partidas oficiais futuras e agendadas. Não se trata de aposta, jogo "
        "de azar ou produto financeiro: é um benefício que devolve o crédito de análise ao usuário "
        "quando a combinação de mercados escolhida por ele, dentre os próprios resultados da "
        "análise gerada pela IA, se confirma no jogo real.\n\n"
        "## 2. Elegibilidade\n\n"
        "2.1 Somente análises do tipo \"partida futura agendada\" (não elegível para análises "
        "independentes). 2.2 Conta verificada e em conformidade com os Termos de Uso. 2.3 Uma "
        "combinação de mercados por análise; a combinação é imutável após confirmada (sem edição "
        "ou cancelamento posterior).\n\n"
        "## 3. Mecânica\n\n"
        "3.1 Ao gerar a análise de uma partida futura, 1 crédito é reservado (ver Política de "
        "Créditos).\n\n"
        "3.2 O usuário monta sua combinação de mercados oferecidos pela própria análise (ex.: "
        "resultado, escanteios, cartões, gols) para participar da campanha promocional, "
        "respeitando o teto de odd combinada de 2,00. Se o usuário não escolher nenhum mercado, o "
        "sistema seleciona automaticamente uma combinação com odd próxima do teto.\n\n"
        "3.3 Após o término oficial da partida (com um intervalo de segurança para consolidação "
        "do resultado oficial via provedor de dados esportivos), o sistema liquida a combinação "
        "automaticamente:\n\n"
        "3.4 Se a combinação escolhida for vencedora: o crédito reservado é consumido — ele "
        "remunera o uso da IA naquela análise.\n\n"
        "3.5 Se a combinação escolhida não for vencedora: o crédito reservado é integralmente "
        "estornado para a carteira do usuário, sem nenhum custo pela análise.\n\n"
        "## 4. O que a promoção não é\n\n"
        "4.1 Não há prêmio em dinheiro, multiplicador de ganhos ou saque de valores: o único "
        "efeito possível é o consumo ou o estorno do crédito já reservado. 4.2 Não é intermediação "
        "de apostas esportivas nem produto de terceiros — a liquidação usa exclusivamente o "
        "resultado oficial da partida para conferir a combinação de mercados da própria análise.\n\n"
        "## 5. Cancelamento, adiamento ou indisponibilidade de dados\n\n"
        "5.1 Se a partida for cancelada oficialmente, adiada sem nova data em prazo razoável, ou "
        "se o resultado oficial não estiver disponível pelo provedor de dados em prazo razoável, "
        "o crédito reservado é estornado integralmente, independentemente de qualquer palpite.\n\n"
        "## 6. Uso indevido\n\n"
        "6.1 Contas múltiplas, manipulação de horário/sistema ou qualquer tentativa de fraudar a "
        "liquidação resultam em cancelamento da participação na campanha, estorno revertido "
        "quando aplicável, e podem levar à suspensão da conta, nos termos dos Termos de Uso.\n\n"
        "## 7. Alterações e encerramento\n\n"
        "7.1 A ApostaInfo pode alterar o teto de odd, os mercados elegíveis ou encerrar a "
        "promoção a qualquer momento, com efeitos apenas sobre análises geradas após a alteração "
        "— combinações já confirmadas seguem a regra vigente no momento da confirmação.\n\n"
        "## 8. Dados esportivos oficiais\n\n"
        "8.1 Os resultados oficiais utilizados para liquidação das campanhas promocionais serão "
        "aqueles disponibilizados pelo provedor oficial de dados esportivos utilizado pela "
        "plataforma.\n\n"
        "8.2 Correções posteriores realizadas pelo fornecedor poderão refletir nos registros da "
        "plataforma.\n\n"
        "## 9. Legislação aplicável\n\n"
        "9.1 Esta promoção é regida pelos mesmos Termos de Uso e Política de Créditos da "
        "plataforma, e pela legislação brasileira aplicável a campanhas promocionais comerciais.",
    ),
    LegalDocumentType.partners_program: (
        "Programa de Parceiros",
        "# Programa de Parceiros\n\n"
        "## 1. O que é o Programa de Parceiros\n\n"
        "1.1 O Programa de Parceiros permite que pessoas físicas ou jurídicas (\"parceiro\") "
        "divulguem a ApostaInfo por meio de um código/link próprio, recebendo comissão comercial "
        "sobre as compras de crédito realizadas por clientes atribuídos a esse código, e "
        "concedendo a esses clientes um cupom de desconto próprio do parceiro.\n\n"
        "1.2 O Programa de Parceiros é independente do programa de indicação entre usuários "
        "comuns (créditos bônus, ver Política de Créditos, seção 6) e não se confunde com ele.\n\n"
        "## 2. Elegibilidade e cadastro\n\n"
        "2.1 A adesão ocorre mediante solicitação (formulário próprio) e aprovação pela "
        "ApostaInfo, que pode recusar ou revogar a qualquer momento, a seu critério, "
        "especialmente em caso de fraude ou descumprimento destes termos.\n\n"
        "2.2 O parceiro deve fornecer dados cadastrais verdadeiros (nome/razão social, CPF/CNPJ, "
        "contato) e manter uma conta de acesso ao portal do parceiro.\n\n"
        "## 3. Comissão comercial\n\n"
        "3.1 A comissão é calculada como percentual ou valor fixo sobre o valor pago em cada "
        "compra de crédito atribuída ao parceiro (por cupom próprio ou por clique em seu link "
        "dentro da janela de atribuição vigente), conforme condições informadas no momento da "
        "aprovação e exibidas no portal do parceiro.\n\n"
        "3.2 A comissão só é considerada devida quando o respectivo pagamento do cliente é "
        "confirmado; pedidos cancelados, estornados ou não pagos não geram comissão.\n\n"
        "## 4. Prazo e forma de pagamento\n\n"
        "4.1 Comissões devidas são pagas em lotes periódicos, por PIX ou transferência, conforme "
        "calendário e método informados no portal do parceiro. O histórico de pagamentos fica "
        "disponível para consulta do próprio parceiro.\n\n"
        "## 5. Nota fiscal e impostos\n\n"
        "5.1 O parceiro é o único responsável por declarar e recolher os tributos incidentes "
        "sobre a comissão recebida, bem como por emitir nota fiscal ou recibo (RPA), quando "
        "exigido por sua situação fiscal (pessoa física ou jurídica). A ApostaInfo pode solicitar "
        "documentação fiscal do parceiro como condição para o pagamento.\n\n"
        "## 6. Cupom e desconto ao cliente indicado\n\n"
        "6.1 O cupom vinculado ao parceiro concede desconto ao cliente no ato da compra. O "
        "desconto ao cliente e a comissão do parceiro são calculados de forma independente, "
        "conforme a Política de Créditos.\n\n"
        "## 7. Fraude e uso indevido\n\n"
        "7.1 São exemplos de uso indevido, sujeitos a cancelamento de comissão e/ou da parceria: "
        "autoindicação (parceiro usando seu próprio código para comprar créditos para si); "
        "criação de contas falsas para gerar comissão artificial; utilização de CPFs de terceiros "
        "sem autorização; e uso automatizado (script, robô ou ferramenta similar) do cupom do "
        "parceiro.\n\n"
        "## 8. Cancelamento e suspensão\n\n"
        "8.1 A ApostaInfo pode pausar ou encerrar a parceria a qualquer momento, em caso de "
        "fraude, descumprimento destes termos ou dos Termos de Uso gerais da plataforma, sem "
        "prejuízo de comissões já devidas por vendas legítimas anteriores à suspensão.\n\n"
        "## 9. Alteração das regras\n\n"
        "9.1 As regras de comissão, desconto e demais condições deste Programa podem ser "
        "alteradas a qualquer momento, com efeito apenas sobre vendas futuras — nenhuma alteração "
        "produz efeito retroativo sobre comissões já devidas ou já pagas.\n\n"
        "## 10. Legislação aplicável\n\n"
        "10.1 Este Programa é regido pelos Termos de Uso e pela legislação brasileira aplicável a "
        "contratos de parceria comercial e comissão mercantil.",
    ),
}


def seed_default_documents(db: Session) -> None:
    if db.execute(select(LegalDocument.id).limit(1)).first() is not None:
        return
    now = datetime.now(timezone.utc)
    for dtype, (title, body) in _DEFAULTS.items():
        db.add(LegalDocument(type=dtype, version=1, title=title, body_md=body,
                             published_at=now, is_current=True))
    db.commit()


def list_current(db: Session) -> list[LegalDocument]:
    return db.execute(
        select(LegalDocument).where(LegalDocument.is_current.is_(True)).order_by(LegalDocument.type)
    ).scalars().all()


def get_current(db: Session, dtype: str) -> LegalDocument:
    try:
        t = LegalDocumentType(dtype)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Tipo de documento inválido.")
    doc = db.execute(
        select(LegalDocument).where(LegalDocument.type == t, LegalDocument.is_current.is_(True))
    ).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento não encontrado.")
    return doc


def accepted_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    return set(db.execute(
        select(UserDocumentAcceptance.document_id).where(UserDocumentAcceptance.user_id == user_id)
    ).scalars().all())


def pending_for_user(db: Session, user_id: uuid.UUID) -> list[LegalDocument]:
    """Documentos vigentes que o usuário ainda NÃO aceitou (na versão vigente)."""
    accepted = accepted_ids(db, user_id)
    return [d for d in list_current(db) if d.id not in accepted]


def accept(db: Session, user_id: uuid.UUID, document_ids: list[str], ip: str | None) -> list[str]:
    current = {d.id: d for d in list_current(db)}
    if document_ids:
        targets = []
        for did in document_ids:
            try:
                u = uuid.UUID(did)
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="ID de documento inválido.")
            if u not in current:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Documento não é a versão vigente.")
            targets.append(u)
    else:
        targets = list(current.keys())  # aceita todos os vigentes

    already = accepted_ids(db, user_id)
    now = datetime.now(timezone.utc)
    newly = []
    for did in targets:
        if did in already:
            continue  # idempotente
        db.add(UserDocumentAcceptance(user_id=user_id, document_id=did, accepted_at=now, ip=ip))
        newly.append(str(did))
    db.commit()
    return newly


def publish(db: Session, dtype: str, title: str, body_md: str, admin_id: uuid.UUID | None) -> LegalDocument:
    """Publica NOVA versão vigente de um tipo (uso administrativo). Exige novo aceite."""
    try:
        t = LegalDocumentType(dtype)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Tipo de documento inválido.")
    prev = db.execute(
        select(LegalDocument).where(LegalDocument.type == t, LegalDocument.is_current.is_(True))
    ).scalar_one_or_none()
    next_version = (prev.version + 1) if prev else 1
    if prev is not None:
        prev.is_current = False
    doc = LegalDocument(type=t, version=next_version, title=title, body_md=body_md,
                        published_at=datetime.now(timezone.utc), is_current=True, created_by=admin_id)
    db.add(doc)
    db.commit()
    return doc
