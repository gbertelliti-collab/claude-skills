# Modo god: engenheiro, mestres de obras e operarios

Tres andares. O ENGENHEIRO (Fable) nao fica na obra: faz analises pontuais. Quem toca tudo, confere e corrige sao os 2 MESTRES DE OBRAS (Opus) com os OPERARIOS (Haiku e Sonnet).

Nomes dos papeis ao despachar (como plugin, o `subagent_type` leva o prefixo `orquestrador:`): `orquestrador:orq-mestre`, `orquestrador:orq-engenheiro`, `orquestrador:orq-leitor`, `orquestrador:orq-executor`, `orquestrador:orq-revisor`. Nas tabelas abaixo o prefixo e omitido.

| andar | modelo | faz | nao faz |
|---|---|---|---|
| ENGENHEIRO (1) | Fable | 3 visitas: a ANALISE que vira a planta, a CONSULTA quando um mestre trava numa decisao, a VISTORIA no fim | acompanhar tarefa, escrever brief de operario, conferir entrega, reler o que o mestre ja conferiu |
| MESTRE DE OBRAS (2) | Opus, papel `orq-mestre` | o ciclo inteiro da skill dentro da sua frente: ficha, quebra, brief, despacho, conferencia, correcao, registro; decide tudo que e so da frente dele | mudar o contrato entre as frentes, sair do escopo, deploy |
| OPERARIOS (varios) | Haiku e Sonnet, papeis `orq-leitor`, `orq-executor`, `orq-revisor` | ler, pesquisar, implementar, testar, revisar | abrir agente, decidir |

## Quando usar

- O usuario pediu: "modo god", "engenheiro", "mestre de obras", "obra grande".
- Ou, por conta propria, so se as TRES valem: (1) o trabalho se parte em 2 frentes com arquivos que nao se tocam; (2) sao umas 8 tarefas ou mais; (3) no modo normal o contexto do chefe encheria de entrega de operario.
- Fora disso, modo normal: cada mestre e um contexto Opus inteiro a mais e o Fable e o modelo mais caro. Obra pequena no modo god sai mais cara e mais lenta.
- So frentes que andam em PARALELO. Trabalho em que a frente B depende do resultado da A e sequencial: fica com 1 chefe (em estudo com 260 configuracoes, tarefa paralelizavel ganhou e tarefa sequencial PIOROU com mais agentes; fontes em `fundamentos.md`).
- A regra do usuario ou do projeto vence. Exemplo: um projeto que proibe agente abrir agente, ou manda todos os operarios em Opus; la o modo god so com ordem expressa do usuario.

## O que custa e por que o engenheiro fica fora

O que custa e reler o contexto a cada resposta, e o contexto de um chefe de sessao longa e muito maior que o de um mestre. Cada passo de coordenacao que sai do chefe e vai pro mestre e uma releitura muito menor. O Fable custa o dobro do Opus em entrada, escrita de cache e saida: por isso so nas 3 visitas, com poucas respostas em cada uma. Mestre e SEMPRE Opus.

O engenheiro e o andar mais caro por resposta: por isso so faz as 3 visitas. Duas regras:

- Obra em modo god comeca em SESSAO NOVA (contexto pequeno). Se a sessao ja esta grande, compacte antes ou diga ao usuario que vale abrir outra.
- A planta sai FECHADA. Adendo no meio da obra e caro (o mestre que recebe adendos faz muito mais respostas e enche o contexto, comparado com o que recebe a planta fechada) e gera contradicao com o que ja foi escrito. Duvida sua antes de despachar: resolva antes.

## Quem e quem na sessao

| a sessao esta em | voce e | os outros |
|---|---|---|
| Fable | o ENGENHEIRO | 2 mestres = 2 agentes `orq-mestre` (Opus) |
| Opus ou outro | o MESTRE 1, que e o MESTRE DA ENTREGA: fica com a frente que CONSOME o contrato (em geral a tela), roda o aceite global e fala com o usuario | mestre 2 = 1 agente `orq-mestre` (Opus); engenheiro = agente `orq-engenheiro` com `model: "fable"` e `description: "[fable:coordenacao] engenheiro: analise"` (depois `consulta`, `vistoria`), retomado por SendMessage pra guardar a memoria da planta |

Nos dois casos o Fable so gasta nas 3 visitas. No registro, mestre e engenheiro sao tipo `coordenacao`.

## Visita 1: a analise (vira a PLANTA)

Um arquivo (scratchpad da sessao, ou `docs/` do projeto se for pra ficar). E o unico canal entre os andares: o que nao esta escrito nela nao existe pro mestre. Leva:

- por que a obra existe (a evidencia, em 5 linhas);
- DECISOES JA TOMADAS: arquitetura e o CONTRATO entre as frentes (assinaturas, nomes de campo, formatos, mensagens de erro, quem consome o que);
- regras do projeto que valem (do README ou das instrucoes do projeto: comando de teste, o que nunca fazer);
- por frente: ESCOPO de arquivos (as duas listas nao tem arquivo em comum), itens numerados, tabela de casos esperados, ACEITE, tetos, caminho do arquivo de estado;
- ACEITE GLOBAL (o que prova que as duas frentes funcionam JUNTAS) e qual mestre e o DA ENTREGA: e ele quem roda o aceite global e a revisao da costura no fim.

Molde: `exemplos/planta-modo-god.md` nesta pasta.

Entregue a planta: 2 agentes `orq-mestre` na MESMA mensagem, em background, `model: "opus"`, `description: "[opus:coordenacao] mestre A: <frente>"`, prompt curto (qual frente, caminho da planta, o que nao coube nela). Diga ao usuario em 1 linha quem esta em que frente. E saia da obra.

## Entre as visitas: o engenheiro fica fora

- Nao edite arquivo de frente, nao escreva no git, nao leia entrega de operario, nao peca status.
- So volta se um mestre chamar ou quando os dois terminarem.

## Visita 2: a consulta (so quando um mestre chama)

O mestre devolve `FALTA_DECISAO` quando a duvida mexe no contrato, na outra frente, em dinheiro/acesso ou em algo sem volta. Ele junta as duvidas numa chamada so, com as opcoes e o custo de cada uma. O engenheiro:

1. decide (olhando so o que a pergunta exige);
2. escreve a decisao na planta;
3. responde ao mestre que perguntou (a sessao por SendMessage; o agente `orq-engenheiro` no retorno final dele, e quem o chamou repassa), e ao outro se a decisao muda o contrato dele.

Duvida que e so da frente o mestre resolve sozinho; se ele trouxer, devolva em 1 linha: "e da sua frente, decida".

## Visita 3: a vistoria

Os dois mestres terminaram. Relatorio de mestre e alegacao, mas quem confere a maquina e mestre, nao engenheiro:

1. Leia os 2 relatorios (STATUS, ACEITE com saida real, EM ABERTO, CONSUMO).
2. Mande o mestre da entrega rodar o ACEITE GLOBAL (a sessao por SendMessage; o agente `orq-engenheiro` pede isso no retorno final dele) e revisar a COSTURA: o lado da outra frente que a frente dele consome. O defeito tipico de obra em duas frentes mora na juncao.
3. Analise o que voltar e olhe voce mesmo SO o que e risco: o contrato dos dois lados e o que mexe em dinheiro, acesso ou producao.
4. Veredito: PODE SUBIR, ou VOLTA pra frente X com o achado exato (teto de 2 voltas por frente; depois replaneje a obra).
5. Fechamento (quem esta na sessao): registrar os mestres (`operarios.py registrar --agente "[opus:coordenacao] mestre A: ..." --frente A ...`), `conferir` (cada mestre com os netos embaixo, todos no modelo pedido), `resumo --por-frente`, `atualizar`; commit por caminho, push e deploy pelas regras do projeto; relatorio pro usuario com o que nao foi verificado.

## Tetos

- 2 mestres. Por mestre: 3 operarios ao mesmo tempo e 8 despachos (a planta pode mudar).
- 3 andares e acabou: os papeis `orq-leitor`, `orq-executor`, `orq-revisor` e `orq-engenheiro` nao tem a ferramenta de abrir agente, e o mestre e proibido de chamar agente generico.
- Mestre que bate no teto para e relata; nao estoura.

## Onde o modo god quebra

| falha | o que fazer |
|---|---|
| engenheiro virando chefe de obra (lendo entrega, pedindo status, conferindo tarefa) | so as 3 visitas; o resto e do mestre |
| engenheiro mandando adendo a planta com a obra andando | planta fechada antes do despacho; mudanca de verdade = consulta registrada na planta, uma vez |
| obra tocada numa sessao velha e enorme | sessao nova ou compactada: cada resposta do engenheiro rele a sessao inteira |
| mestre subindo toda duvida | so sobe contrato, outra frente, dinheiro/acesso e o que nao tem volta; o resto ele decide |
| telefone sem fio: o mestre entende outra coisa | tudo na planta, com tabela de casos; nada "de boca" no prompt |
| contrato implicito entre as frentes | assinatura, campo e mensagem escritos na planta ANTES do despacho |
| mestre fazendo o trabalho do operario (Opus digitando) | o relatorio traz o CONSUMO; mestre com 0 despacho em frente grande = replaneje |
| teto furado (agente demais ao mesmo tempo) | teto e o recurso que limita (memoria, 1 emulador, 1 banco) escritos na planta; conferido no `conferir` |
| operario no modelo errado (o mestre esqueceu o `model`: `orq-*` cai no frontmatter, generico cai na env ou no modelo do mestre) | `model` em TODA chamada do mestre; o `conferir` acusa `SEM-MODELO` |
| um 4o andar (operario abrindo agente) | papeis de operario nao tem a ferramenta; o `conferir` acusa `ANDAR-3` |
| operario recebendo brief vago do mestre | brief desenhado, nivel 3 pra tudo que escreve, com as decisoes da planta coladas LITERAIS |
| erro que cresce de andar em andar | conferencia em todo andar: o operario prova, o mestre roda o aceite, a vistoria olha a costura |
| as duas frentes passam sozinhas e quebram juntas | ACEITE GLOBAL e revisao da costura pelo mestre da entrega, sempre |
