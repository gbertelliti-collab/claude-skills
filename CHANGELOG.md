# Changelog

O plugin não tem número de versão: cada commit na `main` chega em quem instalou (veja "Receber atualizações" no README). As entradas abaixo são por data.

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
