# Fundamentos do orquestrador

De onde saiu cada regra do SKILL.md. Levantado por operarios Haiku/Sonnet e conferido por amostra pelo chefe. Marca: **[MEDIDO]** tem numero de execucao real; **[OFICIAL]** recomendacao da Anthropic; **[USO REAL]** relato de quem usou; **[OPINIAO]** juizo de engenharia sem medicao. "Conferido" = o chefe abriu a fonte e bateu o numero.

Leia so pra mudar uma regra ou um limiar. Nao e pra carregar em todo trabalho.

## 1. Quando delegar

| regra no SKILL.md | evidencia | fonte |
|---|---|---|
| Delegar custa caro; nao delegar tarefa pequena | Agentes gastam ~4x os tokens de um chat; sistema multiagente ~15x **[MEDIDO, conferido]** | anthropic.com/engineering/multi-agent-research-system |
| Delegar busca/leitura/pesquisa; cuidado com codigo acoplado | Multiagente ganhou 90,2% do Opus 4 sozinho em pesquisa em largura; a maior parte do trabalho de codigo tem menos partes paralelizaveis **[MEDIDO/OFICIAL, conferido]** | idem |
| Nao delegar o que depende de contexto compartilhado ou vai-e-vem | Docs do Claude Code: trabalho iterativo e mudanca rapida e direcionada nao vao pra subagente **[OFICIAL]** | code.claude.com/docs/en/sub-agents |
| Operario nao deixa a resposta mais inteligente | Subagente da paralelismo e olhar novo, nao resposta melhor por si so **[OFICIAL]** | code.claude.com/docs/en/best-practices |
| Papeis sob demanda, nao esteira | Em projeto Laravel de producao a delegacao ficou ansiosa demais: tarefa simples virava explorador -> executor -> testador -> revisor; apertar o contrato reduziu o vai-e-vem **[USO REAL, conferido]** | github.com/donvito/codex-astra-luna-orchestrator/issues/5 |
| Decisoes acopladas ficam com o chefe | Subagentes em paralelo tomam decisoes implicitas conflitantes; agente linear unico e o padrao seguro **[OPINIAO]** | cognition.com/blog/dont-build-multi-agents |
| Falhas vem mais do desenho que do modelo | MAST: 14 modos de falha em 3 categorias (desenho do sistema, desalinhamento entre agentes, verificacao), 1600+ execucoes anotadas **[MEDIDO, conferido no resumo]**; proporcoes por modo (repeticao de passo 15,7%, verificacao incorreta 9,1%) lidas pelo operario, nao conferidas | arxiv.org/abs/2503.13657 |

## 2. Brief

| regra | evidencia | fonte |
|---|---|---|
| OBJETIVO, ENTREGA, FONTES, ESCOPO | A Anthropic pede 4 coisas ao delegar: objetivo, formato de saida, orientacao de ferramentas e fontes, limites claros. Brief curto gerou trabalho duplicado e mal interpretado **[OFICIAL, conferido]** | anthropic.com/engineering/multi-agent-research-system |
| ACEITE executavel no brief | Nao esta na Anthropic; vem do sous-chef (bloco de verificacao que o chefe roda) e do Superpowers **[USO REAL]** | github.com/tomascupr/sous-chef, obra/superpowers |
| Resumo de ate 15 linhas; saida grande em arquivo | Subagente explora com dezenas de milhares de tokens e devolve 1.000-2.000; saida grande vai pra armazenamento externo com referencia leve **[OFICIAL]** | anthropic.com/engineering/effective-context-engineering-for-ai-agents |
| No maximo 3 avisos por brief | Reflexion limita a memoria a 1-3 experiencias **[MEDIDO, conferido]**; o numero ideal pra brief e **[OPINIAO]** | arxiv.org/abs/2303.11366 |
| Exemplo de brief que funcionou | ExpeL: licao + exemplo recuperado foi melhor que so licao (HotpotQA 39% x 36%; ALFWorld 59% x 50%; ReAct puro 28% e 40%) **[MEDIDO, conferido]** | arxiv.org/abs/2308.10144 |
| Escala (1 leitor / 2-4 / mais) | Prompt do agente lider da Anthropic: fato simples = 1 agente com 3-10 chamadas; comparacao = 2-4 subagentes; 3-5 em paralelo **[OFICIAL]** (regra de pesquisa, adaptada pra codigo por juizo) | anthropic.com/engineering/multi-agent-research-system |

## 3. Rota de modelo e aprendizado

| regra | evidencia | fonte |
|---|---|---|
| Barato primeiro, sobe quando a conferencia falha | Cascata economiza muito (FrugalGPT ate 98% no cenario deles; AutoMix >50%) **[MEDIDO, nao conferido]** | arxiv.org/abs/2305.05176, arxiv.org/abs/2310.12963 |
| Sem ACEITE executavel nao desce de modelo | No AutoMix o ganho some quando o verificador e ruidoso **[MEDIDO, nao conferido]** | arxiv.org/abs/2310.12963 |
| Haiku em leitura, Sonnet em edicao (rota padrao) | Guia da Anthropic indica Haiku pra tarefa de subagente e menor custo; benchmarks citados dao Haiku bem abaixo do Sonnet em tarefa de terminal **[OFICIAL + citado]**. Nao existe medicao publica Haiku x Sonnet por tipo de tarefa de codigo: por isso a ficha mede aqui | platform.claude.com/docs/en/about-claude/models/choosing-a-model |
| Limiares (4 tarefas, 60%, 80%, 3 falhas seguidas, reteste em 30 dias) | **[OPINIAO]**: nenhum paper da limiar. Sao constantes no topo do `operarios.py`; ajuste com o historico real | - |
| Evidencia por nivel de brief | Achado de revisor: prova com brief 3 nao vale pra brief 2 (reproduzido) | registro local |
| Licao so de tarefa que passou; erro so de falha confirmada | ExpeL: extrair licao a partir de reflexoes piorou o resultado (29% x 39%), e extrator mais fraco tambem (32% x 39%) **[MEDIDO, conferido]** | arxiv.org/abs/2308.10144 |
| Avisos vencem sozinhos | So contam os ultimos 20 registros do par: erro que parou de acontecer sai da ficha (equivale a remover licao sem confirmacao, como no ExpeL) | - |
| `conferir` le o modelo real | Bug aberto de subagente ignorando o modelo, com relato de 1.149 de 1.371 subagentes rodando em Opus (espelho de terceiro, nao conferido); #43869 aberta **[conferido]** | github.com/anthropics/claude-code/issues/43869 |
| `model` sempre explicito | "Modelo mais capaz disponivel" foi resolvido errado com a sessao acima do Opus **[USO REAL, conferido]** | github.com/obra/superpowers/issues/2096 |

## 4. Conferir, corrigir, contexto

| regra | evidencia | fonte |
|---|---|---|
| O chefe roda o ACEITE; "feito" e alegacao | MAST tem categoria inteira de falha de verificacao; implementador reportou DONE com processo ainda vivo **[MEDIDO + USO REAL]** | arxiv.org/abs/2503.13657, obra/superpowers#2430 |
| Aceite tem que conseguir falhar | Reflexion: teste gerado pelo proprio agente deu falso positivo em 16,3% no MBPP x 1,4% no HumanEval **[MEDIDO, conferido]** | arxiv.org/abs/2303.11366 |
| Teto de 3 rodadas; sem progresso troca de operario | Repetir com o mesmo agente tende a repetir o erro (MAST, repeticao de passo); sous-chef para por arvore igual ou mesma falha; em teste local, 2 de 2 chefes sem a skill assumiram a tarefa apos 2 voltas iguais e 2 de 2 com a 1a versao da skill reenviaram pro mesmo operario **[MEDIDO local, n pequeno]**. A ordem exata da escada e **[OPINIAO]** | github.com/tomascupr/sous-chef, teste local |
| Teste direcionado por tarefa, suite no fim; resumo no contexto | Porte de 15 tarefas: 39 subagentes, contexto do coordenador em 830 mil tokens sem compactar, US$ 154,83, 53 execucoes da suite inteira **[USO REAL, conferido]** | github.com/obra/superpowers/issues/2612 |
| Revisor so pra julgamento | Revisor gastava 5 a 9 min em fato que o controlador resolve com 1 comando **[USO REAL]** | obra/superpowers#2054 |
| Sem escrita no git com executor vivo | Controlador commitou arquivos de um implementador em background **[USO REAL]** | obra/superpowers#2520 |
| Executor nao apaga por curinga | Subagente apagou temporarios de outros no scratchpad compartilhado **[USO REAL, so titulo lido]** | anthropics/claude-code#104804 |
| Arquivo de estado em trabalho longo | Queda no meio re-despachou trabalho ja commitado; sous-chef guarda o contador em arquivo e le o arquivo apos compactar **[USO REAL]** | obra/superpowers#2293, tomascupr/sous-chef |
| Achado menor vai pro relatorio | Achados adiados sumiram junto com a pasta de trabalho **[USO REAL]** | obra/superpowers#2253 |

## O que o uso real ensinou

- Em uso real medido, cerca de 80% do custo foi reler contexto a cada resposta (cache), nao o que se escreve: cortar respostas rende mais que cortar texto; brief e relatorio desenhados custam menos de 1%.
- Papeis de agente criados no meio de uma sessao so ficam disponiveis em sessao nova; o caminho alternativo (agente generico mais as regras coladas) funciona.
- Sem a definicao dos tipos de tarefa, o chefe classificou uma migracao grande como edicao simples e mandou pro modelo barato; dai a tabela de tipos e a regra "na duvida, logica".
- Revisor independente achou defeitos que os testes do executor nao pegavam, inclusive regressoes introduzidas pelas CORRECOES; desfazer a correcao e ver o teste cair pega teste que nao prova nada.
- Parte dos erros foi do brief do chefe, nao do operario (mensagem de erro que o outro lado nao tratava, teste nao exigido): confira quem consome o que o brief decidiu.
- No modo god, a planta fechada antes do despacho evita adendos caros e contradicoes, e o engenheiro presente demais vira o andar mais caro; premissa de fato na planta leva `arquivo:linha`, e o operario deve dizer "nao achei" em vez de confirmar.

Precos de API citados em qualquer lugar mudam: confira os precos atuais antes de usar os numeros.

## 6. O que nao tem evidencia

- Ordem exata da escada de correcao e todos os limiares numericos.
- Se brief nivel 3 pro Haiku sai mais barato que Sonnet com brief 2 (o chefe gasta token caro pra escrever o brief). A ficha mostra os dois; decida pelo custo da leitura que o brief exige.
- Medicao propria de custo em dinheiro: o registro guarda tokens de saida e contexto maximo por tarefa, sem converter em preco.
