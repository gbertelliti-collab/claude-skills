<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/banner-escuro.svg">
  <img alt="orquestrador: plugin do Claude Code com um chefe que pensa e confere, operários Haiku e Sonnet que leem e digitam, e uma ficha que aprende quem deve receber a próxima tarefa" src="docs/img/banner-claro.svg" width="100%">
</picture>

<p align="center">
  <img alt="Plugin do Claude Code" src="https://img.shields.io/badge/Claude%20Code-plugin-D97757">
  <img alt="Python 3, sem dependências" src="https://img.shields.io/badge/Python%203-sem%20depend%C3%AAncias-3776AB">
  <img alt="91 testes no motor" src="https://img.shields.io/badge/testes%20do%20motor-91-2ea44f">
  <img alt="Licença MIT" src="https://img.shields.io/badge/licen%C3%A7a-MIT-blue">
  <img alt="Último commit" src="https://img.shields.io/github/last-commit/gbertelliti-collab/claude-skills?label=%C3%BAltimo%20commit">
</p>

<p align="center">
  <a href="#números-de-uso-real">Uso real</a> ·
  <a href="#como-funciona">Como funciona</a> ·
  <a href="#instalar">Instalar</a> ·
  <a href="#receber-atualizações">Atualizações</a> ·
  <a href="#como-usar">Como usar</a> ·
  <a href="#o-que-vem-no-plugin">O que vem</a>
</p>

Sessão longa do Claude Code em modelo grande fica cara porque relê o contexto inteiro a cada resposta. O **orquestrador** faz a sessão trabalhar como chefe: ela quebra o trabalho em partes independentes, entrega cada parte a um operário barato (Haiku ou Sonnet) com um brief desenhado, confere a entrega rodando o aceite ela mesma e registra o resultado. Desse registro sai uma ficha que diz, por tipo de tarefa, qual modelo recebe a próxima e quanto detalhe o brief precisa.

```bash
claude plugin marketplace add gbertelliti-collab/claude-skills
claude plugin install orquestrador@gbertelli-skills
```

Depois é só pedir trabalho com 2 ou mais partes ("usa os operários", "divide o trabalho", "faz em paralelo").

## Números de uso real

Tudo abaixo saiu do registro do próprio motor e dos transcripts do Claude Code, em trabalho de verdade entre 15 e 17/11/2026. Nada é estimativa: são contagens. O retrato agregado está em [`docs/uso-real.json`](docs/uso-real.json) e os gráficos são gerados dele por [`docs/graficos.py`](docs/graficos.py).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/numeros-escuro.svg">
  <img alt="140 tarefas delegadas em 3 dias, 4 sessões e 8 projetos; 82% aprovadas de primeira (115 de 140); 2 voltaram para o chefe e outras 23 fecharam em até 2 rodadas de correção; 3,1% do custo em tokens foi o que gastaram os 130 agentes Haiku e Sonnet" src="docs/img/numeros-claro.svg" width="100%">
</picture>

### O que os operários acertam e onde erram

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/tipos-escuro.svg">
  <img alt="Resultado por tipo de tarefa: revisão 36 de 36 de primeira, leitura 30 de 31, edição lógica 12 de 25, front 13 de 21, pesquisa web 9 de 9, coordenação 5 de 5, texto 5 de 5, teste 2 de 4, outros três tipos 3 de 4" src="docs/img/tipos-claro.svg" width="100%">
</picture>

- **Ler, pesquisar e revisar quase não dá errado:** 75 de 76 tarefas passaram de primeira. É o que mais vale delegar, e o Haiku deu conta de todas as 28 que recebeu.
- **Escrever código é onde a conferência paga:** em edição lógica e front, 25 de 46 passaram de primeira. Das outras 21, 20 fecharam porque o chefe rodou o aceite, viu falhar e mandou corrigir, em vez de aceitar o "feito" do operário; 1 o chefe terminou.
- **Quase nada volta para o chefe:** das 25 que não passaram de primeira, 23 o próprio operário corrigiu em até 2 rodadas e 2 o chefe terminou.

| modelo | tarefas | de primeira | respostas por tarefa | saída por tarefa | contexto máximo |
|---|---:|---:|---:|---:|---:|
| Haiku | 32 | 31 (97%) | 4 | 13 mil tokens | 103 mil |
| Sonnet | 82 | 68 (83%) | 11 | 17 mil tokens | 105 mil |
| Opus | 26 | 16 (62%) | 114 | 182 mil tokens | 381 mil |

As três últimas colunas são medianas. O Opus não é o pior da tabela: ele recebeu as tarefas mais difíceis (edição lógica pesada, telas grandes, coordenação de frente), que são longas e raramente saem de primeira com qualquer modelo. Cada tarefa dele tem dez vezes o tamanho de uma do Sonnet.

<details>
<summary>Tabela completa: tipo de tarefa por modelo</summary>

<br>

Cada célula é "passaram de primeira / tarefas".

| tipo | Haiku | Sonnet | Opus |
|---|---:|---:|---:|
| revisão | | 30 / 30 | 6 / 6 |
| leitura | 22 / 22 | 8 / 9 | |
| edição lógica | | 10 / 17 | 2 / 8 |
| front | | 12 / 17 | 1 / 4 |
| pesquisa web | 6 / 6 | 2 / 2 | 1 / 1 |
| coordenação | | | 5 / 5 |
| texto | | 5 / 5 | |
| teste | 1 / 2 | 1 / 1 | 0 / 1 |
| edição mecânica | 2 / 2 | | |
| debug | | | 1 / 1 |
| outro | | 0 / 1 | |

</details>

### Para onde vai o custo

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/custo-escuro.svg">
  <img alt="Parcela dos agentes e parcela do custo por modelo: Opus 59,0% dos agentes e 71,8% do custo; Fable 3,5% dos agentes e 25,1% do custo; Sonnet 27,2% dos agentes e 3,0% do custo; Haiku 10,4% dos agentes e 0,1% do custo" src="docs/img/custo-claro.svg" width="100%">
</picture>

Medição do `custo.py` nas mesmas 4 sessões, inteiras: 346 agentes (os 4 chefes de sessão entram na conta) e 17.515 respostas.

- **Modelo barato trabalhando quase não aparece na conta:** os 130 agentes Haiku e Sonnet são 38% dos agentes e 3,1% do custo.
- **O que custa é reler, não escrever:** 78% do custo é reler contexto a cada resposta (46% leitura de cache, 32% escrita de cache). O que os modelos escrevem é 22%.
- **Por papel:** os chefes de sessão ficam com 34%; agentes genéricos (`general-purpose`), 24%; executores `orq-executor`, 21%; revisores, 2,6%; mestres do modo god, 1,1%; leitores, 0,2%. Os 18% restantes são agentes de fora do plugin.
- **O que a simulação diz:** 20% menos respostas corta 20% do custo. Encolher em 20 mil tokens o contexto inicial de cada agente corta 3,3%. Por isso a skill manda juntar chamadas e escrever brief bem desenhado, em vez de economizar no texto do brief.

### O que a ficha aprendeu sozinha

Lições que o registro guardou de tarefas que passaram de primeira e que hoje entram nos briefs seguintes:

| tipo | lição |
|---|---|
| leitura | Perguntas fechadas, cada uma com letra, e a ordem de responder "não diz" quando o material não diz. A resposta volta conferível linha a linha. |
| pesquisa web | Pedir o trecho copiado, não parafraseado, e ler a documentação pelo `.md` da página: o resumo automático troca palavras. |
| edição lógica | Listar no brief todas as ocorrências do padrão (um grep), não só a do achado. O operário conserta uma e deixa a irmã. |
| front | CSS do operário em arquivo próprio, com prefixo obrigatório em todo seletor. Não vaza para o resto e confere com 1 grep. |
| teste | Ambiente pronto pelo chefe e roteiro numerado: 9 checagens de primeira em 3,5 minutos. |
| revisão | Pedir prova por execução. Numa revisão do motor, 15 achados e os 15 confirmados. |
| coordenação | Planta com os fatos já medidos e aceite numérico: uma frente inteira em 16 respostas do mestre. |

> [!NOTE]
> Leia os números com o tamanho que eles têm: um usuário, 3 dias, 140 tarefas. "De primeira" quer dizer que passou na primeira conferência do chefe, que roda o aceite ele mesmo. Custo é token ponderado pelo preço de API de cada modelo, não fatura. A sua ficha começa vazia e vai chegar aos seus próprios números.

## Como funciona

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/ciclo-escuro.svg">
  <img alt="Ciclo do chefe: ficha, quebrar, brief, despachar, conferir e registrar. Se a entrega não passa na conferência, volta para correção em até 3 rodadas. O registro alimenta a ficha, e a próxima tarefa do mesmo tipo já sai com rota e avisos." src="docs/img/ciclo-claro.svg" width="100%">
</picture>

- **O chefe decide, o operário executa.** Arquitetura, regra de negócio, deploy e o veredito de "pronto" ficam com a sessão. Operário recebe objetivo, escopo, fontes, restrições, formato de entrega e o aceite que será rodado.
- **"Feito" sem prova não é feito.** O chefe roda o aceite ele mesmo, e aceite que não consegue falhar não vale: em dinheiro, acesso e segurança, desfaz a mudança, vê o teste cair e restaura.
- **Quem erra ganha brief melhor antes de modelo maior.** A escada é brief mais desenhado, depois mais esforço, depois um modelo acima. Na terceira rodada sem resolver, o chefe faz.
- **A rota é medida, não opinião.** Um modelo mais barato só vira a rota de um tipo de tarefa depois de provar que aguenta, e a ficha propõe o experimento onde ainda não há prova.
- **O modelo que rodou é conferido.** `operarios.py conferir` lê no transcript o modelo real de cada operário e acusa quem saiu diferente do pedido.

### Os papéis

| papel | modelo padrão | faz | não faz |
|---|---|---|---|
| `orq-leitor` | Haiku | busca, leitura, pesquisa com fonte | editar arquivo |
| `orq-executor` | Sonnet | código, teste, script de dados, tela, texto, só nos arquivos do escopo | decidir design, sair do escopo |
| `orq-revisor` | Sonnet (Opus em dinheiro e segurança) | revisar a entrega de outro e dar veredito | consertar |
| `orq-mestre` | Opus | tocar uma frente inteira no modo god | mudar o contrato entre as frentes |
| `orq-engenheiro` | Fable | as 3 visitas do modo god | despachar operário, editar código |

### Modo god, para obra grande

Quando o trabalho se parte em 2 frentes que não se tocam e passa de umas 8 tarefas, o chefe vira engenheiro e sai da obra: faz 3 visitas (a análise que vira a planta, a consulta quando um mestre trava, a vistoria no fim) e deixa 2 mestres de obras tocando os operários.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/modo-god-escuro.svg">
  <img alt="Modo god: um engenheiro em Fable faz 3 visitas (planta, consulta, vistoria); 2 mestres de obras em Opus tocam uma frente cada, cada um com leitor Haiku, executor Sonnet e revisor Sonnet." src="docs/img/modo-god-claro.svg" width="100%">
</picture>

No uso real, 34 dos 346 agentes rodaram assim, no segundo andar (operário aberto por um mestre), e custaram 0,9% do total; os 3 mestres somaram 1,1%. O andar caro é o engenheiro, e é por isso que ele só faz visita. Detalhes em [`modo-god.md`](plugins/orquestrador/skills/orquestrador/modo-god.md).

## Instalar

No terminal:

```bash
claude plugin marketplace add gbertelliti-collab/claude-skills
claude plugin install orquestrador@gbertelli-skills
```

Dentro de uma sessão, o equivalente é `/plugin marketplace add gbertelliti-collab/claude-skills` e `/plugin install orquestrador@gbertelli-skills`. Confira com `claude plugin list` e abra uma sessão nova: papéis instalados no meio de uma sessão só aparecem na seguinte.

**Requisitos**

- Claude Code com suporte a plugins e marketplaces.
- Python 3 no PATH (`python`, `python3` ou `py -3`). O motor usa só a biblioteca padrão.
- Os modelos `haiku`, `sonnet` e `opus` disponíveis na conta (e `fable`, se for usar o engenheiro do modo god).
- Opcional, para a skill `provar-na-tela`: a CLI `playwright-cli`, ou o navegador embutido do app desktop do Claude Code, ou Chrome, Chromium ou Edge com o pacote Python `websocket-client`.

## Receber atualizações

O Claude Code só liga atualização automática sozinho nos marketplaces oficiais. Em marketplace de terceiro, como este, ela vem desligada e quem publica não consegue ligar por você. É um ajuste, uma vez só:

1. Numa sessão, rode `/plugin` e abra a aba **Marketplaces**.
2. Selecione `gbertelli-skills` e escolha **Enable auto-update**.

Daí em diante cada mudança deste repositório chega sozinha. O Claude Code confere em segundo plano nos primeiros minutos de cada sessão, avisa `Plugin updated: orquestrador · Run /reload-plugins to apply` e, mesmo que você ignore o aviso, a versão nova já vale na sessão seguinte.

O plugin não fixa número de versão de propósito: assim cada commit conta como versão nova e nenhuma melhoria fica presa esperando alguém lembrar de subir o número.

Para atualizar na mão, sem ligar nada:

```bash
claude plugin marketplace update gbertelli-skills
claude plugin update orquestrador@gbertelli-skills
```

<details>
<summary>Para um time: ligar a atualização automática por configuração</summary>

<br>

Em `settings.json` (do usuário, do projeto ou gerenciado pela organização), a entrada do marketplace aceita `autoUpdate`:

```json
{
  "extraKnownMarketplaces": {
    "gbertelli-skills": {
      "source": { "source": "github", "repo": "gbertelliti-collab/claude-skills" },
      "autoUpdate": true
    }
  }
}
```

As variáveis `DISABLE_AUTOUPDATER=1` e `DISABLE_UPDATES=1` desligam também a atualização de plugins; `FORCE_AUTOUPDATE_PLUGINS=1` mantém a dos plugins ligada mesmo assim.

</details>

## Como usar

Peça trabalho com 2 ou mais partes independentes e a skill abre sozinha. Também dá para chamar pelo nome: `/orquestrador:orquestrador`. Um exemplo de como a conversa anda, num projeto fictício:

```text
você   adiciona o limite de estoque no carrinho e mostra o erro na tela. usa os operários

chefe  Ficha lida. São 3 partes:
         [haiku:leitura]         mapear quem chama adicionarItem
         [sonnet:edicao-logica]  regra do limite + testes (2 arquivos)
         [sonnet:front]          mensagem de erro na tela do carrinho
       Despachei a leitura e a regra. Enquanto isso escrevo o brief da tela.

chefe  Leitura voltou: 3 chamadores, todos passam pela mesma função.
       Regra voltou: rodei os testes, passaram; desfiz a checagem e os 2 casos
       de erro caíram, então o teste prova. Tela despachada. Falta só ela.

chefe  Pronto. operarios: 3 tarefas, 3 de primeira | haiku fez 1 de 3
```

O brief que o executor recebeu nesse exemplo está inteiro em [`exemplos/brief-nivel3-edicao.md`](plugins/orquestrador/skills/orquestrador/exemplos/brief-nivel3-edicao.md): trecho atual colado, decisão literal, tabela de casos e um aceite que consegue falhar.

### O motor

```bash
python <pasta da skill>/operarios.py <status|ficha|registrar|conferir|resumo|atualizar>
python <pasta da skill>/custo.py [--do-registro]
```

O Claude Code informa a pasta da skill quando ela carrega, e quem roda esses comandos no dia a dia é o próprio chefe. Para ter ideia do que sai, isto é um trecho da ficha real depois das 140 tarefas (lições encurtadas):

```text
leitura -> haiku brief 2 (rota padrao)
  licao: conferir doc pelo curl do .md da pagina; o WebFetch resume
  stats: haiku b1 1a 1/1 ok 1/1; b2 1a 19/19 ok 19/19 ~10k | sonnet b2 1a 8/9 ok 8/9 ~22k
edicao-logica -> sonnet brief 3 (rota padrao)
  licao: dar no brief TODAS as ocorrencias do padrao (grep), nao so a do achado
  stats: sonnet b2 1a 0/1 ok 1/1; b3 1a 10/16 ok 16/16 ~27k | opus b2 1a 0/5 ok 5/5 ~272k; b3 1a 2/3 ok 3/3
teste -> sonnet brief 3 (rota padrao)
  experimento: haiku brief 3 (sem prova com brief 3 (n=2); feitos 2 de 4)
  stats: haiku b3 1a 1/2 ok 2/2 ~61k | sonnet b3 1a 1/1 ok 1/1 ~8k | opus b2 1a 0/1 ok 1/1 ~215k
```

Como ler: `b2 1a 19/19` é "com brief nível 2, 19 de 19 passaram de primeira"; `ok` conta também as que fecharam depois de correção; `~10k` é a saída mediana em tokens. A ficha olha os últimos 20 registros de cada par, então erro que parou de acontecer sai sozinho. E a linha que fecha um trabalho, também real:

```text
operarios: 140 tarefas, 115 de primeira, 23 corrigidas, 0 escaladas, 2 falharam | haiku 31/32 de primeira; sonnet 68/82 de primeira; opus 16/26 de primeira | saida: haiku 0,41M · sonnet 0,73M · opus 3,8M | haiku fez 32 de 140
```

### Configuração (tudo opcional)

| variável | para que serve | padrão |
|---|---|---|
| `ORQ_REGISTRO` | arquivo do registro de tarefas | `~/.claude/orquestrador/registro.jsonl` |
| `ORQ_FICHA` | arquivo `.md` onde `operarios.py atualizar` grava a ficha | sem ela, `atualizar` só avisa e sai com código 0 |
| `ORQ_PROJECTS` | pasta dos transcripts do Claude Code | `~/.claude/projects` |

- **Nome dos agentes:** agente de plugin leva o prefixo do plugin, então o `subagent_type` é `orquestrador:orq-leitor`, `orquestrador:orq-executor` e assim por diante. Se a sua versão do Claude Code mostrar os agentes sem prefixo, use o nome simples.
- **`PROJETOS.md`:** `provar-na-tela` e `bater-valores` leem um `PROJETOS.md` opcional na pasta de cada skill (como subir, entrar e conferir cada projeto seu). Copie o `PROJETOS.exemplo.md` e preencha; sem ele, as skills usam o README do projeto.

## O que vem no plugin

| skill | quando abre | o que faz |
|---|---|---|
| [`orquestrador`](plugins/orquestrador/skills/orquestrador/SKILL.md) | trabalho com 2 ou mais partes independentes | o ciclo completo: ficha, quebra, brief, despacho, conferência, correção e registro, além do modo god |
| [`auditoria-adversarial`](plugins/orquestrador/skills/auditoria-adversarial/SKILL.md) | "varredura", "auditoria do projeto", "análise adversarial" | varre o projeto inteiro com vários agentes, prova cada achado e corrige no mesmo dia |
| [`provar-na-tela`](plugins/orquestrador/skills/provar-na-tela/SKILL.md) | antes de dizer "pronto" numa mudança visual | abre a tela de verdade, tira o print e compara com o pedido |
| [`bater-valores`](plugins/orquestrador/skills/bater-valores/SKILL.md) | "não bate", "faltando", "pagou 2x" | roteiro para divergência de valor, com as causas comuns e a prova |

```text
.claude-plugin/marketplace.json     o marketplace (gbertelli-skills)
plugins/orquestrador/
  .claude-plugin/plugin.json        o plugin (sem número de versão: cada commit é uma versão)
  agents/                           os 5 papéis orq-*
  skills/
    orquestrador/
      SKILL.md                      o ciclo do chefe
      modo-god.md                   engenheiro, mestres de obras e operários
      fundamentos.md                de onde saiu cada regra, com fonte e marca de medido ou opinião
      operarios.py                  registro, ficha, conferência de modelo, resumo
      custo.py                      para onde foram os tokens
      exemplos/                     briefs e planta prontos para copiar
      tests/                        91 testes do motor
    auditoria-adversarial/
    provar-na-tela/
    bater-valores/
docs/
  uso-real.json                     os números agregados deste README
  graficos.py                       gera os gráficos a partir deles
```

Para rodar os testes:

```bash
cd plugins/orquestrador/skills/orquestrador
python -m unittest discover -s tests
```

Para gerar o mesmo retrato com o seu uso (lê o seu registro e os seus transcripts, grava só números agregados):

```bash
python docs/graficos.py --coletar
```

## Privacidade

O repositório traz só números agregados do uso: nenhum brief real, nenhum nome de projeto e nenhuma tabela de projetos. A ficha de quem instala começa vazia e aprende com o próprio uso. O registro, a ficha e o `PROJETOS.md` que você preencher ficam só na sua máquina (estão no `.gitignore`).

## Licença

[MIT](LICENSE). Pode usar, copiar, mudar e redistribuir, mantendo o aviso de copyright.
