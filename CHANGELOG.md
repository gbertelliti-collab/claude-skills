# Changelog

O plugin não tem número de versão: cada commit na `main` chega em quem instalou (veja "Receber atualizações" no README). As entradas abaixo são por data.

## 2026-11-24: design tem tipo, autor e prova próprios

O registro dizia que as telas iam bem (14 de 16 de primeira nas 24 horas anteriores) e o dono achou o visual de um site inteiro ruim: "de primeira" media o aceite de build e teste, não a tela. A prévia aprovada tinha sido refeita por 13 operários Sonnet, um pedaço cada, sem skill de design. Detalhe no README ("Design é a exceção").

### Novo

- **Tipo `design`** (tela que o dono julga pelo olho: página nova, redesenho, acabamento, portar prévia aprovada). Rota Opus brief 3, sem promoção para modelo menor e sem experimento. A ficha e a nota trazem a linha `regra:`.
- **Agente `orq-designer`** (Opus): autor de uma tela inteira. Abre a skill de design, trabalha com a referência na mão e prova por print em desktop e celular.
- **`operarios.py reprovar --id X | --agente "descrição" --erro "classe: detalhe"`.** Marca numa tarefa já registrada que a entrega foi reprovada depois: `de_primeira` vira `corrigido`, soma uma rodada, grava o erro com classe e `reprovado: true`. Só aquela linha do registro muda; uma cópia fica em `registro.jsonl.antes-de-reprovar`.
- **Avisos novos no hook de despacho:** design em Sonnet ou Haiku, design para o `orq-executor`, brief de design sem print, brief de design sem referência visual, e `front` com cara de design (uma vez por sessão).
- **Dois avisos no `registrar`:** tela (`front` ou `design`) registrada de primeira lembra que só vale com o print visto e já mostra o comando `reprovar` com o id; revisão sem `--achados/--confirmados` avisa que o placar do revisor fica sem dado (em um dia de uso, só 3 de 8 revisões tinham placar).
- **Seção "Design: a exceção ao delega tudo" no `SKILL.md`** e parágrafo correspondente no `modo-god.md`.

- **Referência vem dos projetos anteriores do dono.** Antes de desenhar, o chefe procura o que o dono já aprovou (`DESIGN.md`, tokens, telas prontas de um projeto parecido, notas de gosto) e leva o caminho no brief; o `orq-designer` aceita o `DESIGN.md` de um projeto anterior como referência de projeto novo. No caso que originou esta entrada, o site só melhorou depois que o dono pediu isso.

### Mudou

- `front` passou a ser só ligar tela que já tem visual definido (componente, estado, dado). Os registros antigos de `front` não foram reclassificados.

### Corrigido

- **Registro com separador de linha Unicode sumia da ficha.** Uma linha do registro com U+2028, U+2029 ou U+0085 dentro de um campo era lida como duas linhas inválidas: a tarefa não entrava na ficha e o `reprovar` e o `reclassificar` não achavam o id. O `registrar` nunca grava esses caracteres; o defeito só aparecia em linha vinda de fora (edição à mão, outra ferramenta). O motor agora corta o registro só em quebra de linha comum.
- **`custo.py` contava o `orq-designer` e o `orq-engenheiro` como "outros".** Os dois têm linha própria na tabela por papel.

## 2026-11-23: aviso na hora do despacho

As regras de despacho (modelo explícito, etiqueta `[modelo:tipo]`, ACEITE no brief) só eram cobradas depois, pelo `conferir` e pelo `registrar`. Agora o plugin avisa no momento em que o chefe abre o operário.

### Novo

- **Hook de despacho (`hooks/despacho.sh`, PreToolUse da ferramenta de abrir agente).** Devolve ao chefe um aviso curto quando o despacho de um operário da skill sai sem `model`, sem `[modelo:tipo]`, com tipo que não existe, com etiqueta e `model` divergentes, com tarefa de escrita para o leitor ou o revisor, com brief sem ACEITE, com Opus ou Fable em execução contra a rota da ficha, ou com experimento aberto para o tipo (os dois últimos, uma vez por sessão e por tipo). Só avisa: nunca bloqueia, nunca decide permissão e nunca altera a chamada. Agente que não é da skill passa sem nada, e o script nem chama o Python para ele.
- **`operarios.py despacho`.** O mesmo teste na mão: recebe o JSON da chamada na entrada padrão e lista os avisos; `--hook` é o formato que o Claude Code lê.
- **`ORQ_SEM_AVISO_DESPACHO=1`** desliga o aviso.

## 2026-11-23: melhorias tiradas de nove dias de uso real

O registro do autor tinha 267 tarefas em 12 projetos. A análise dele e dos transcripts dos operários mostrou onde a skill falhava; os números estão no README ("O que nove dias de uso mudaram no plugin") e em `fundamentos.md`.

### Novo

- **Tamanho da tarefa.** Escrita que o operário fechou em menos de 30 respostas até a primeira entrega passou de primeira 78% das vezes; com 30 ou mais, 45%. O `registrar` grava `respostas_1a` (lido do transcript, sem contar a correção), a ficha abre com a linha `tamanho:` quando o seu registro já mostra a diferença, e a skill ganhou a regra "um objetivo por tarefa".
- **Falta do brief não pune o modelo.** Rodada registrada como `corrigido` com `--licao` e sem `--erro` não conta contra o modelo na rota, e a ficha mostra a lição em `faltou no brief:`. Antes, três rodadas por brief incompleto faziam a ficha mandar subir o effort do modelo.
- **Placar de revisão.** `registrar --achados N --confirmados M` em tarefa de revisão; a ficha soma por modelo de revisor.
- **`operarios.py reclassificar`.** `--listar` mostra os erros gravados sem classe; `--id <id> --classe <classe>` conserta, guardando uma cópia do registro.
- **Linha de fechamento.** O `resumo` mostra `opus em execucao: N tarefas, X de saida, K de primeira` e `grandes: N de M de escrita, K de primeira` quando houver.
- **Avisos do `registrar`.** Depois de gravar, ele avisa quando a tarefa era grande e precisou de correção, quando uma tarefa pequena passou de primeira e a próxima vale o experimento no modelo mais barato, e quando a linha não ensina nada (sem `--erro` e sem `--licao`).

### Mudou

- **Classe de erro obrigatória.** `--erro` sem classe conhecida agora é recusado (exit 13, nada gravado) com a lista das classes. Antes caía calado em `outro`: 29 de 35 erros do registro estavam assim, e a ficha quase não gerava aviso. Variações como `escopo-incompleto:` e `segurança:` são aceitas.
- **Regra de modelo.** A skill passa a dizer: tarefa difícil pede tarefa menor e brief mais desenhado antes de modelo maior. No registro, o Opus como executor passou 9 de 24 de primeira e respondeu por metade da saída.

## 2026-11-17: o plugin avisa quando não está recebendo atualizações

Marketplace de terceiro nasce com a atualização automática desligada, e quem publica não consegue ligar por ninguém. Quem instalava ficava parado na versão do dia da instalação sem saber.

### Novo

- **Aviso na primeira sessão.** Um hook de início de sessão percebe que a atualização automática do marketplace está desligada e pede ao Claude que avise e pergunte se você quer ligar. No máximo uma vez por semana e três vezes no total; nunca liga sozinho; quem desligou de propósito não é avisado.
- **`operarios.py atualizacao`.** Sem opção, diz se está ligada e por quê. `--ligar` acrescenta `autoUpdate: true` na entrada do marketplace no `settings.json` do usuário, sem mexer no resto, e guarda uma cópia do arquivo. `--nao-perguntar` cala o aviso, assim como `ORQ_SEM_AVISO_ATUALIZACAO=1`.
- **App desktop.** O app desktop abre toda sessão com `DISABLE_AUTOUPDATER=1`, o que desliga também a atualização de plugins. Nesse caso o `--ligar` grava também `FORCE_AUTOUPDATE_PLUGINS=1` em `env`.

### Corrigido

- **O hook de retomada não rodava em Linux nem em macOS.** O script montava o caminho do motor com um padrão que o `sh` desses sistemas não entende, não achava o motor e saía calado. No Windows funcionava. Os dois scripts de hook agora cortam o caminho de um jeito que vale em qualquer `sh`, e há testes que executam os scripts de verdade nos três sistemas.

## 2026-11-17: a skill cede para o fluxo que o projeto já tem

Retorno de quem instalou num projeto que não é de código: a skill abria sozinha em trabalho com várias partes e podia passar por cima de um fluxo próprio, em que a redação vai para um agente especialista.

### Mudou

- **Fluxo do projeto vence, e só na parte dele.** Se o `CLAUDE.md` ou um agente do próprio projeto já diz quem faz um tipo de tarefa, essa parte vai para ele; o orquestrador cuida do resto. Em projeto sem dono definido para a tarefa nada muda: a skill continua abrindo sozinha. A regra está na descrição da skill e no começo da "Regra de uso". O agente do projeto roda no modelo que o projeto definiu: antes, quando a skill abria, ela trocava o modelo dele.
- **README:** seção "Se você já tem um fluxo próprio", com as três formas de limitar quando a skill abre.

## 2026-11-17: onda de melhorias a partir de projetos parecidos

Pesquisa em orquestradores públicos, na documentação de plugins do Claude Code e em ferramentas de custo. As fontes de cada regra nova estão em `fundamentos.md`.

### Novo

- **Retomada depois de compactar.** `operarios.py retomar` lista o que a sessão já despachou e ainda não registrou. O plugin traz um hook de início de sessão que roda isso sozinho depois que o contexto compacta ou a sessão é retomada. Sem operários, não imprime nada.
- **Comando `/orquestrador:placar`.** Mostra o que a sessão despachou, quem acerta de primeira por modelo e para onde foi o token. Só abre quando você digita.
- **Preços editáveis no `custo.py`.** `--precos tabela.json` (ou a variável `ORQ_PRECOS`) sobrescreve preços sem mexer no script, `--mostrar-precos` imprime a tabela atual, e a saída passa a dizer de onde vieram os preços e que o valor é estimativa.
- **Cor por papel.** Cada agente `orq-*` tem uma cor na lista de tarefas e no transcript.
- **Regra nova na skill:** operário derrubado por limite de uso sobe para o modelo seguinte e é registrado como `anulado`.
- **Arquivos de comunidade:** guia de contribuição, política de segurança, modelos de issue e de pull request.
- **Teste da estrutura do plugin** a cada push: cadastro, skills, agentes e hook conferidos sem chamar modelo.

### Mudou

- O `SKILL.md` do orquestrador chama o motor por `${CLAUDE_SKILL_DIR}`, que o Claude Code troca pela pasta da skill ao carregar. Antes o texto dizia `<pasta desta skill>`.
- O cadastro do plugin ganhou `homepage`, `repository` e `keywords`.

## 2026-11-17: publicação

- Plugin `orquestrador` com 4 skills, 5 agentes e o motor em Python sem dependências.
- README com números de uso real gerados de `docs/uso-real.json`, em português e inglês, com imagens para tema claro, escuro e tela estreita.
- Testes do motor em Linux, macOS e Windows a cada push.
- Licença MIT.
