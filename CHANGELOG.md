# Changelog

O plugin não tem número de versão: cada commit na `main` chega em quem instalou (veja "Receber atualizações" no README). As entradas abaixo são por data.

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
