# claude-skills

Marketplace de plugin do Claude Code com 1 plugin, o **orquestrador**: um jeito de a sessão do Claude Code (o "chefe") dividir trabalho em partes independentes, despachar operários baratos (Haiku e Sonnet) com briefs bem desenhados, conferir cada entrega e aprender, pelo histórico, qual modelo recebe a próxima tarefa de cada tipo.

## O que vem no plugin

- **Skills**
  - `orquestrador`: o ciclo completo (ficha, quebra, brief, despacho, conferência, correção, registro) e o modo god (engenheiro, mestres de obras e operários).
  - `auditoria-adversarial`: varredura de um projeto inteiro com vários agentes, achado provado e correção no mesmo dia.
  - `provar-na-tela`: olhar a tela de verdade antes de dizer "pronto" numa mudança visual.
  - `bater-valores`: roteiro para divergência de valor ("não bate", "faltando", "pagou 2x"), com causas comuns e prova.
- **Agentes**: `orq-leitor`, `orq-executor`, `orq-revisor`, `orq-mestre`, `orq-engenheiro`.
- **Motor** (`operarios.py` e `custo.py`, Python sem dependências): registra como cada operário se saiu, gera a ficha com a rota recomendada por tipo de tarefa e mede o consumo de tokens dos transcripts.

## Como instalar

Em um terminal:

```bash
claude plugin marketplace add gbertelliti-collab/claude-skills
claude plugin install orquestrador@gbertelli-skills
```

Dentro de uma sessão do Claude Code o equivalente é `/plugin marketplace add gbertelliti-collab/claude-skills` e `/plugin install orquestrador@gbertelli-skills`. Para conferir: `claude plugin list`. Depois de instalar, abra uma sessão nova: papéis criados no meio de uma sessão só aparecem nas seguintes.

Quem clonou o repositório pode usar o caminho da pasta no lugar do endereço (`claude plugin marketplace add ./claude-skills`) e validar com `claude plugin validate ./claude-skills`.

## Como usar

- Peça trabalho com 2 ou mais partes independentes ("usa os operários", "divide o trabalho", "faz em paralelo") e a skill `orquestrador` abre sozinha. Ela também pode ser chamada pelo nome, como `/orquestrador:orquestrador`.
- O motor roda com `python <pasta da skill>/operarios.py <status|ficha|registrar|conferir|resumo|atualizar>`. O Claude Code informa a pasta da skill quando ela carrega.
- Para obra grande em duas frentes, peça "modo god": um engenheiro faz 3 visitas pontuais e 2 mestres de obras tocam os operários.
- `provar-na-tela` e `bater-valores` usam um arquivo `PROJETOS.md` opcional na pasta de cada skill. Copie o `PROJETOS.exemplo.md` para `PROJETOS.md` e preencha com os seus projetos; sem ele, as skills usam o README do projeto.

### Variáveis de ambiente (todas opcionais)

| variável | para que serve | padrão |
|---|---|---|
| `ORQ_REGISTRO` | arquivo do registro de tarefas | `~/.claude/orquestrador/registro.jsonl` |
| `ORQ_FICHA` | arquivo `.md` onde `operarios.py atualizar` grava a ficha | sem ela, `atualizar` só avisa no stderr e sai com código 0 |
| `ORQ_PROJECTS` | pasta dos transcripts do Claude Code | `~/.claude/projects` |

## Nome dos agentes

Um agente de plugin é namespaced pelo nome do plugin, então os papéis aparecem como `orquestrador:orq-leitor`, `orquestrador:orq-executor` e assim por diante, e é esse nome que vai em `subagent_type`. Se o Claude Code mostrar os agentes sem esse prefixo na sua versão, use o nome simples.

## Requisitos

- Claude Code com suporte a plugins e marketplaces.
- Python 3 no PATH como `python` (ou `python3` / `py -3`; só biblioteca padrão). Os testes rodam com `cd plugins/orquestrador/skills/orquestrador && python -m unittest discover -s tests`.
- Opcionais, para a skill `provar-na-tela`: a skill/CLI `playwright-cli`, ou o navegador embutido do app desktop do Claude Code, ou Chrome/Chromium/Edge com o pacote Python `websocket-client` (controle por CDP).
- Os modelos `haiku`, `sonnet`, `opus` (e `fable`, se você usar o modo god com engenheiro) precisam estar disponíveis na sua conta.

## O que não está aqui

Nenhum registro de uso, nenhum brief real e nenhuma tabela de projetos: a ficha começa vazia e aprende com o seu uso. O `PROJETOS.md` que você preencher fica só na sua máquina (está no `.gitignore`). Ainda não há arquivo de licença.
