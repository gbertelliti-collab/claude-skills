---
name: orquestrador
description: Usa em TODO trabalho com 2 ou mais partes independentes, ANTES de comecar a fazer sozinho - feature em varios arquivos, tela nova mais servidor, auditoria ou revisao ampla, migracao, bug que cruza componentes, lote de tarefas parecidas, pesquisa com varias fontes - e pra revisar codigo nao trivial que voce mesmo escreveu antes de subir. Tambem quando o usuario falar "orquestra", "orquestrar", "use a skill orquestrar", "usa os operarios", "joga pros agentes", "modo chefe", "modo god", "engenheiro", "mestre de obras", "manda o haiku/sonnet fazer", "divide o trabalho", "faz em paralelo", "como os operarios estao indo", "ficha dos modelos". Tarefa que o proprio projeto ja entrega a alguem (agente especialista do projeto ou regra no CLAUDE.md dizendo quem faz, ex.: redacao vai pro agente redator) continua com ele: nao abra esta skill por cima, salvo se o usuario pedir pelo nome. NAO usa pra edicao de 1 ou 2 arquivos, pergunta rapida ou tarefa de 1 a 3 chamadas de ferramenta.
---

# Orquestrador: chefe + operarios que aprendem

A sessao e o chefe: pensa, decide, confere e integra. Operarios Haiku e Sonnet leem e digitam. Toda tarefa delegada vira 1 linha no registro; a ficha que sai do registro diz quem recebe a proxima tarefa daquele tipo e quanto detalhe o brief leva.

Motor: `python "${CLAUDE_SKILL_DIR}/operarios.py" <status|ficha|registrar|reclassificar|conferir|retomar|resumo|atualizar|atualizacao>` (`--help` em cada um; sem `python` na maquina, use `python3` ou `py -3`). `atualizacao` diz se o plugin recebe versao nova sozinho; `atualizacao --ligar` so depois de o usuario aceitar. O registro fica em `~/.claude/orquestrador/registro.jsonl` (a variavel `ORQ_REGISTRO` muda o caminho). A ficha em arquivo so e gravada se `ORQ_FICHA` apontar pra um arquivo `.md`. Obra grande em duas frentes: `modo-god.md` nesta pasta. O porque de cada regra, com fonte: `fundamentos.md` (so pra mudar regra).

Os papeis (`orq-leitor`, `orq-executor`, `orq-revisor`, `orq-mestre`, `orq-engenheiro`) vem no mesmo plugin. Como plugin, o `subagent_type` leva o prefixo do plugin (`orquestrador:orq-leitor`); no resto do texto o prefixo e omitido.

## Regra de uso

- Fluxo do projeto vence, e so na parte dele. Se o CLAUDE.md ou um agente do PROPRIO projeto ja diz quem faz um tipo de tarefa (ex.: toda redacao vai pro agente redator do projeto), essa parte vai pra ele, com o agente e o modelo que o projeto manda: nao troque por `orq-*`. O resto do trabalho segue este ciclo normalmente, e isso vale tambem quando o usuario pediu a skill pelo nome. Projeto sem dono definido pra tarefa (a maioria) = regra normal, a skill abre sozinha.
- O usuario pediu a skill (com qualquer das palavras da descricao): o primeiro despacho sai NESSA resposta.
- Trabalho com 2 ou mais partes independentes: `ficha` e quebra ANTES de editar qualquer arquivo.
- Ao despachar, 1 linha pro usuario: quem foi (modelo) pra que, e o que VOCE faz enquanto isso. Durante o trabalho, toda resposta diz quem esta vivo e o que falta. Se o usuario perguntar quem esta trabalhando, o que falta ou se acabou: responda antes.
- Nunca espere parado: com operario rodando, faca a parte que e so sua ou prepare o proximo brief; ninguem trabalhando e ainda falta coisa = puxe a proxima etapa na hora.
- Operario e burro de proposito (modelo barato, sem o contexto da conversa): recebe tudo DESENHADO (passo 4). Brief vago e erro do chefe.
- Operario e revisor sao agentes Claude. A regra do usuario ou do projeto vence (outra ferramenta ou outro revisor so se ele pedir).

| pensamento | realidade |
|---|---|
| "ja estou com tudo na cabeca, faco mais rapido sozinho" | use sem esperar o usuario pedir. Leitura e revisao rodam em paralelo enquanto voce faz a parte acoplada |
| "as partes dependem uma da outra" | a decisao depende de voce; leitura, tela em arquivo proprio, teste e revisao quase nunca |
| "explicar da mais trabalho que fazer" | o brief e o que te obriga a decidir; e o operario rende sem encher o seu contexto |
| "termino isto e depois divido" | divida agora: o que voce esta fazendo e uma das partes |

## Delegar ou fazer direto

Operario nao deixa a resposta mais inteligente: ele da paralelismo, olhar novo e contexto limpo no chefe. Cada um nasce com 90 a 120 mil tokens de contexto.

| delega | o chefe faz |
|---|---|
| busca, leitura e pesquisa com saida grande (repo, logs, docs, web) | 1 a 3 chamadas de ferramenta; ou junte varias pequenas num operario so |
| implementacao estreita, independente, em arquivos proprios | partes acopladas entre si, ou que dependem do vai-e-vem da conversa |
| a REPETICAO: aplicar em N arquivos o padrao que ja ficou pronto no 1o | decisao de arquitetura, API, schema, dependencia, regra de negocio |
| revisao independente (quem nao viu o raciocinio acha mais) | o que fazer com cada achado; integracao; veredito de pronto |
| lote de tarefas parecidas | deploy, push, delete, migracao em producao, mensagem pra terceiro |

Papeis sao sob demanda, nao esteira: nao rode leitor -> executor -> testador -> revisor por reflexo.

## Economia de tokens

Em uso real medido, o que custa e RELER o contexto a cada resposta (leitura + escrita de cache = 80% do custo), nao o que se escreve (20%). Num exemplo medido, quem mais gastou foi o agente generico (perto de metade, quase todo no modelo maior), depois o chefe (cerca de um terco, com contexto de centenas de milhares de tokens por resposta); os operarios `orq-*` somaram poucos por cento.
- Menos respostas, nao menos brief: chamadas independentes na MESMA mensagem, ler so o trecho, nao reabrir arquivo, operario devolve uma vez. 20% menos respostas = 20% menos custo (o custo cresce junto com o numero de respostas).
- Brief desenhado e barato e evita a rodada de correcao, que e cara. Nao economize no brief nem no relatorio do operario (cortar os dois mexe em menos de 1%).
- Execucao nunca em `general-purpose` ou `claude`: papel `orq-*` com `model`. Opcional: a env `CLAUDE_CODE_SUBAGENT_MODEL=sonnet` faz agente SEM `model` nascer em Sonnet em vez de herdar o modelo da sessao; quer Opus, passe `model: "opus"` na chamada, com motivo. Opus em executor so com motivo escrito. Mestre e Opus, nao Fable. (Vale pra agente generico; um `orq-*` sem `model` usa o `model` do frontmatter dele, e `Explore`/`Plan` nao mudam com a env.) A regra do usuario ou do projeto vence.
- Contexto do chefe pequeno: resumo de operario, saida grande em arquivo (gravado por `orq-executor`: leitor e revisor nao gravam), nada de colar diff ou log; nao acorde so pra olhar status; fechou uma obra, compacte ou abra sessao nova antes da proxima.
- Nao faca: cache de 1 hora em subagente (piora 8%); tirar o arquivo de instrucoes do projeto dos operarios (ganha 0,8% e eles perdem as regras do projeto).
- Onde foi o token desta sessao: `python "${CLAUDE_SKILL_DIR}/custo.py"` (`--do-registro` pra todas as sessoes).

## Ciclo

**1. Ficha.** `operarios.py ficha` uma vez no comeco (`--tipo <tipo>` pra um so). Por tipo: modelo, nivel de brief, effort, avisos (com o que reforcar no brief), licoes, o que faltou no brief nas ultimas vezes, exemplo de brief que funcionou, custo mediano e experimento sugerido. No topo, a linha `tamanho:` quando o seu registro ja mostra a diferenca entre tarefa pequena e grande.

**2. Quebrar.** Cada tarefa tem um tipo, arquivos donos (um escritor por arquivo) e um ACEITE que o chefe roda sozinho. Primeiro o dominio; so o codigo que nao e tela, teste nem banco se divide em mecanica x logica:

| tipo | e isto |
|---|---|
| `busca` | achar onde esta: arquivo, simbolo, uso. A resposta sao ponteiros |
| `leitura` | ler e resumir material dado: codigo, log, doc, issue |
| `pesquisa-web` | fato de fora da maquina, com fonte |
| `front` | tela, componente, estilo (mesmo quando e repeticao) |
| `teste` | escrever ou ajustar teste |
| `dados-sql` | query, migration, script de dados |
| `edicao-logica` | resto do codigo que exige entender: funcao + chamadas, refactor, feature |
| `edicao-mecanica` | resto do codigo especificado por inteiro, sem decisao: trocar valor, renomear, repetir um padrao |
| `debug` | achar a causa de um erro |
| `texto` | redacao: doc, mensagem, texto de tela |
| `revisao` | revisar a entrega de outro |
| `coordenacao` | mestre de obras e engenheiro do modo god |
| `outro` | o que nao couber acima |

Na duvida entre mecanica e logica: logica. Tipo errado suja a ficha do tipo certo.

Tamanho: um OBJETIVO por tarefa de escrita. Em uso real medido, escrita que o operario fechou em menos de 30 respostas ate a primeira entrega passou de primeira 78% das vezes; com 30 ou mais, 45%, e a correcao custou mais de um quarto de toda a saida dos executores. O tamanho do brief nao preve isso (brief mais longo acertou MAIS); o que preve e a tarefa carregar varios objetivos. Sinais de que sao duas tarefas: titulo com "e" ou com lista ("regra X, tela Y e prova Z"), mais de um ACEITE, conserto de varios achados sem relacao, investigar E consertar. Quebre por objetivo; o que depende do anterior vai em sequencia, no mesmo dono de arquivo.

Escala: fato simples = 1 leitor; comparacao ou mapa de repo = 2 a 4 leitores; codigo = 1 leitor pra mapear, o chefe decide, 1 a 3 executores de arquivos separados. Teto padrao de 4 ao mesmo tempo; o usuario ou o README do projeto podem dar outro (anote o teto e o recurso que limita: memoria, um emulador so, um banco). Passou do teto: segure a revisao e o que depende de outra tarefa; entram na 1a vaga. Mais de 5 tarefas: arquivo de estado (1 linha por tarefa), escrito so pelo chefe; depois de compactar ou retomar a sessao, leia o arquivo e rode `retomar` (o que a sessao despachou e ainda nao registrou; o hook do plugin ja traz isso sozinho). Duas frentes que nao se tocam e 8 ou mais tarefas: `modo-god.md`.

**3. Rota.** Use modelo, brief e effort da ficha; pode divergir com motivo de 1 linha.

- O que o usuario disse na sessao sobre modelo ou quantidade de agentes vence a ficha na hora, e a regra do projeto tambem. Registre do mesmo jeito, com o motivo.
- Tarefa que so da pra conferir por opiniao (texto, design, decisao) nao vai pro modelo mais barato: descer de modelo so compensa quando a conferencia pega o erro.
- Modelo maior em execucao nao compra acerto. Em uso real medido, o modelo maior como executor (tarefa grande, brief nivel 2) passou de primeira 9 de 24 vezes e gastou metade de toda a saida; o intermediario, com brief nivel 3 e tarefa pequena, 3 em cada 4. Tarefa dificil pede brief mais desenhado e tarefa menor ANTES de modelo maior. O `resumo` mostra `opus em execucao: ...` quando isso acontece.
- `experimento:` na ficha = ela ainda nao sabe se o modelo mais barato aguenta aquele tipo. Aceite nas tarefas mais mecanicas do tipo (a repeticao), com ACEITE executavel, ate fechar os 4 (`feitos K de 4`), e registre com `--experimento`. Sem isso o Sonnet faz tudo e a ficha nunca aprende o que o Haiku aguenta.

**4. Brief.** O brief e o contrato, nesta ordem:

```
OBJETIVO: 1 resultado concreto
ESCOPO: arquivos/pasta/pergunta exatos (executor edita so estes)
FONTES: onde olhar e com que comando ou ferramenta
CONTEXTO: o minimo - caminho, linha, padrao existente pra copiar, decisoes ja tomadas
RESTRICOES: o que nao pode mudar + gotchas do projeto que valem aqui
AVISOS: os avisos da ficha pra este modelo+tipo, literais (no maximo 3)
ENTREGA: formato e tamanho maximo (resumo de ate 15 linhas; saida grande vai pra arquivo e volta o caminho; so `orq-executor` grava arquivo)
ACEITE: o comando ou checagem que o chefe vai rodar
```

Brief DESENHADO e o padrao: o operario nao conhece a conversa, o projeto nem a sua decisao. Tudo que ele precisa esta escrito; nada de "entenda e resolva". Exemplos prontos de brief nivel 2 e nivel 3: `exemplos/` nesta pasta.

- Nivel 2 (padrao de busca, leitura, pesquisa e revisao): todos os campos, com caminho e linha em CONTEXTO, o comando pronto em FONTES e o formato exato da ENTREGA.
- Nivel 3 (padrao de tudo que ESCREVE): nivel 2 + o trecho atual colado + passo a passo numerado + tabela de casos esperados (entrada -> saida) + o que NAO fazer + "pare e devolva FALTA_CONTEXTO se <condicao>".
- Nivel 1 (so OBJETIVO, ESCOPO, FONTES, ENTREGA, ACEITE) e excecao: so quando a ficha provar que o tipo aguenta.
- Decisao sua (ou da planta) entra LITERAL: assinatura, nome de campo, mensagem, valor. Parafrasear e telefone sem fio. Premissa de fato leva `arquivo:linha`.
- Aviso da ficha (`cuidado: ... -> no brief: <reforco>`): cumpra o reforco. Se ela mostrar `exemplo:`, leia e siga o molde (um brief real que passou de primeira).
- Ajudar o operario que erra e nesta ordem: brief mais desenhado, depois effort, depois modelo maior.

**5. Despachar.**

| tipo | papel (`subagent_type`) |
|---|---|
| busca, leitura, pesquisa-web; debug que so le log e codigo | `orquestrador:orq-leitor` |
| edicao-*, teste, dados-sql, front, texto, outro; debug que mexe | `orquestrador:orq-executor` |
| revisao | `orquestrador:orq-revisor` |
| coordenacao (so no modo god) | `orquestrador:orq-mestre`, `orquestrador:orq-engenheiro` |

- `model` explicito em TODA chamada (o alias da ficha: `haiku`, `sonnet`, `opus`). `effort` so quando a ficha mandar.
- `description` = `[modelo:tipo] resumo`, unica na sessao: o `registrar --agente` e o `conferir` usam.
- Independentes na mesma mensagem, em background; espere a notificacao, nao leia o arquivo de saida.
- Papel `orq-*` nao existe na sessao (aberta antes da instalacao do plugin)? `general-purpose` com o mesmo `model` e a ordem de ler o arquivo `agents/orq-<papel>.md` do plugin orquestrador.
- Enquanto um executor esta vivo, o chefe nao escreve no git (add, commit, stash, checkout) nem edita os arquivos dele.
- Brief barrado pelo classificador de seguranca, ou tarefa que nem rodou: reescreva o enquadramento ou faca voce, e registre `anulado`.
- Operario derrubado por limite de uso ou erro de API (nao por erro dele): redespache no modelo seguinte da escada com o mesmo brief e registre `anulado` pro que caiu.

**6. Conferir** (o chefe, nunca a palavra do operario):

- Rode o ACEITE voce mesmo: o direcionado por tarefa, a suite inteira uma vez no fim.
- Aceite que nao consegue falhar nao e aceite: teste novo tem que cair sem a mudanca. Em dinheiro, acesso ou seguranca, prove: desfaca a mudanca (ou desligue o gate), rode o teste, veja cair e restaure o arquivo.
- Tudo que tranca acesso ou mexe em valor sai do executor COM teste que exercita o caminho real; se o brief nao pediu, o erro e do brief.
- Sem como executar no ambiente (sem compilador, sem aparelho): ACEITE = conferencia estatica (grep por item, leitura do trecho, tipos se houver) + revisor independente + UM teste no fim feito por voce, com tudo junto. Operario nao promete o que nao rodou.
- Arquivos tocados x ESCOPO (`git diff --name-only`); fora do escopo e revertido ou explicado.
- "Testado"/"feito" sem saida real colada = nao feito. FEITO_COM_RESSALVA, TRAVADO e PARCIAL = nao passou (passo 7). FALTA_CONTEXTO = o chefe responde ou decide e reenvia; nao conta como rodada.
- Fato mecanico (existe? compila? quantas ocorrencias?) voce checa com 1 comando; nao gaste revisor nisso.
- Pesquisa e leitura: confira por amostra 1 ou 2 afirmacoes que pesam na decisao.
- Revisor independente quando ha JULGAMENTO em jogo: codigo nao trivial, ou dinheiro/folha/seguranca/migracao (ai com `opus`). Mudanca mecanica provada por grep ou print nao precisa. Nunca o proprio executor. Ele revisa tambem as CORRECOES (regressao, correcao que nao corrige, teste que nao prova).
- Mensagem de erro, codigo de status ou nome de campo que voce decidiu no brief: confira quem CONSOME do outro lado antes de despachar.
- Cada achado do revisor voce reproduz ou le no codigo (CONFIRMADO/REFUTADO) antes de mandar corrigir. Revisao sem linha `VEREDITO:` falhou. Achado menor nao corrigido vai pro relatorio final. Registre a revisao com `--achados N --confirmados M`: a ficha passa a mostrar quanto cada modelo de revisor acha de verdade, e e isso que decide Sonnet ou Opus na revisao.

**7. Corrigir** (teto de 3 rodadas por tarefa):

| rodada | quando | o que o chefe faz |
|---|---|---|
| 1 | a entrega nao passou | SendMessage pro MESMO operario: achado exato (arquivo:linha, esperado x obtido) + saida real do ACEITE |
| 2 | houve progresso (falha diferente ou menor) | mesmo operario, brief mais desenhado |
| 2 | sem progresso (mesma falha, diff igual, ou "feito" com o ACEITE falhando) | operario NOVO, um modelo acima, brief nivel 3, com "a tentativa anterior falhou em X" |
| 3 | ainda falha | o chefe faz |

Atalho: se, pra escrever o proximo brief, voce ja achou a causa e o conserto cabe em ate 3 chamadas de ferramenta, faca agora e registre `falhou` pro operario.

**8. Registrar** cada tarefa ao fechar, a que deu certo E a que deu errado, antes de seguir:

```
python "${CLAUDE_SKILL_DIR}/operarios.py" registrar --agente "[haiku:front] cartao na lista de clientes" --resultado escalado --rodadas 2 --brief 3 --experimento --erro "escopo: nao trocou o cartao na versao de celular" --erro "borda: lista vazia quebrava" --projeto meu-app
python "${CLAUDE_SKILL_DIR}/operarios.py" registrar --agente "[sonnet:front] cartao na lista de clientes" --resultado de_primeira --rodadas 0 --brief 3 --licao "colar o cartao pronto e listar os 2 arquivos (desktop e celular)" --projeto meu-app
python "${CLAUDE_SKILL_DIR}/operarios.py" registrar --tipo leitura --modelo sonnet --resultado anulado --rodadas 0 --brief 2 --projeto meu-app --tarefa "servicos exportados (brief barrado pelo classificador)"
python "${CLAUDE_SKILL_DIR}/operarios.py" registrar --agente "[sonnet:revisao] revisao do cartao" --resultado de_primeira --rodadas 0 --brief 2 --achados 4 --confirmados 3 --projeto meu-app
```

- `--agente` = a `description` do despacho: o script le no transcript o modelo que rodou DE VERDADE, o tipo, os tokens, quem e o mestre, e guarda o brief como exemplo quando passou de primeira. Sem transcript (tarefa `anulado`): `--tipo` e `--modelo` na mao.
- `resultado`: `de_primeira` (passou na 1a conferencia), `corrigido` (passou depois de N rodadas no mesmo modelo), `escalado` (subiu de modelo; registre tambem a linha de quem pegou), `falhou` (o chefe fez), `anulado` (nao rodou ou foi barrado; nao conta na ficha).
- `--brief`: o nivel que voce usou no despacho. A ficha aprende por nivel.
- `--erro "classe: detalhe"`: so falha do OPERARIO confirmada por checagem, UM erro por flag. Classes: `escopo`, `contrato`, `borda`, `estado`, `desempenho`, `teste`, `alegacao`, `leitura`, `visual`, `seguranca`, `outro` (o que cada uma e: `registrar --help`). E a classe que vira AVISO, por isso e obrigatoria: sem classe conhecida o `registrar` recusa (exit 13, nada gravado) e lista as classes; `outro` so quando nenhuma couber. Erro antigo gravado sem classe: `reclassificar --listar`, depois `reclassificar --id <id> --classe <classe>` (uma por erro).
- `--licao`: so em tarefa que passou: o ajuste de brief ou de rota que funcionou.
- Rodada causada por brief incompleto ou errado (o operario fez o que foi pedido): `corrigido` com a `--licao` do que faltou no brief e SEM `--erro`. A ficha nao conta essa rodada contra o modelo e mostra a licao em `faltou no brief:`. `corrigido` sem `--erro` e sem `--licao` nao ensina nada.
- `--achados N --confirmados M`: so em revisao (passo 6).
- O `registrar` pode responder com `AVISO:` (tarefa grande, candidata ao experimento no modelo mais barato, linha que nao ensina): aplique na PROXIMA tarefa.

**9. Fechar.**

- `operarios.py conferir`: modelo pedido x modelo real de cada operario da sessao. Exit 3 = problema (modelo divergiu, neto sem modelo, andar a mais): diga no relatorio. Exit 10 = nenhum operario na sessao.
- `operarios.py atualizar`: regrava a ficha no arquivo de `ORQ_FICHA`. Sem a variavel, so avisa e sai 0.
- `operarios.py resumo`: a linha `operarios: N tarefas, X de primeira... | saida: ... | haiku fez A de N` do relatorio (mais `opus em execucao: ...` e `grandes: ...` quando houver: sao os dois lugares pra onde o token costuma ir).
- Relatorio: o que foi feito, como foi conferido, o que nao foi verificado, achados menores em aberto.

## Modo god (resumo; antes de usar leia `modo-god.md` inteiro)

Tres andares. O ENGENHEIRO (Fable) nao fica na obra: faz 3 visitas (a analise que vira a planta com o contrato entre duas frentes, a consulta quando um mestre trava numa decisao, a vistoria no fim). 2 MESTRES DE OBRAS (`orq-mestre`, Opus) tocam tudo: rodam este ciclo cada um na sua frente, com os OPERARIOS Haiku e Sonnet recebendo tudo desenhado. So quando o usuario pedir, ou com 2 frentes de arquivos separados que andam em paralelo e umas 8 tarefas ou mais. Regra do projeto vence.

## Erros comuns

| erro | o que fazer |
|---|---|
| delegar tarefa minuscula ou acoplada; esteira completa em tarefa simples | faca direto, junte, ou use so o papel que a tarefa pede |
| Sonnet em tudo, experimento nunca aceito | feche os 4 do experimento na repeticao |
| brief "entenda e resolva" | desenhe: trecho, passos, casos, o que nao fazer |
| dois executores no mesmo arquivo | um dono por arquivo |
| colar diff ou log inteiro no contexto do chefe | operario devolve resumo; saida grande em arquivo, por `orq-executor` |
| suite inteira a cada tarefa | teste direcionado por tarefa, suite no fim |
| registrar so o que deu certo, ou `falhou` no que nem rodou | registre tudo; o que nao rodou e `anulado` |
| `--erro` sem classe, ou varios erros num `--erro` so | `classe: detalhe`, um por flag (sem classe o `registrar` recusa) |
| tarefa com varios objetivos num operario so | um objetivo por tarefa; lista vira N tarefas |
| subir pro modelo maior porque a tarefa e dificil | brief nivel 3 e tarefa menor primeiro |
| repetir a mesma correcao no mesmo operario | sem progresso = operario novo um modelo acima |
| operario decidindo design | o brief traz a decisao; FALTA_CONTEXTO volta pro chefe |

## Limites

- O Claude Code deixa subagente abrir subagente ate 3 andares abaixo da sessao e 20 rodando ao mesmo tempo. Aqui: `orq-leitor`, `orq-executor`, `orq-revisor` e `orq-engenheiro` nao tem a ferramenta de abrir agente; so o `orq-mestre` do modo god abre, e so um andar.
- Agente aberto sem `model`: a doc (sub-agents, "Choose a model") usa o primeiro destes: `model` da chamada > `model` do frontmatter > `CLAUDE_CODE_SUBAGENT_MODEL` > modelo de quem abriu. Um `orq-*` sem `model` cai no frontmatter dele; um generico cai na env (aqui `sonnet`) ou no modelo de quem abriu; `Explore` e `Plan` ignoram a env. Passe `model` em toda chamada mesmo assim: o `conferir` acusa `SEM-MODELO` e `ANDAR-3`.
- A skill nao troca o modelo da sessao: o chefe e o modelo da sessao.
- Modelo ignorado no subagente tem bug aberto (anthropics/claude-code#43869): o `conferir` le o modelo real no transcript.
