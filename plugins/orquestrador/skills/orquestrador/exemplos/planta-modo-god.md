# PLANTA (exemplo curto de modo god) - projeto ficticio "loja-exemplo"

Engenheiro: a sessao principal. 2 frentes, cada uma com 1 mestre de obras (`orquestrador:orq-mestre`, Opus). Operarios: Haiku e Sonnet.
Scratch (so arquivos de trabalho): `<pasta temporaria da sessao>`. Projeto no registro: `loja-exemplo`. Sem git nesta obra: o chefe commita no fim.

## Por que a obra existe

- O carrinho aceita quantidade maior que o estoque (cliente ve "comprado" e depois recebe cancelamento).
- A tela do carrinho nao mostra erro nenhum quando o servidor recusa.

## Decisoes ja tomadas (CONTRATO; mestre nao muda)

- O servidor responde `409` com corpo `{ "erro": "ESTOQUE_INSUFICIENTE", "disponivel": <inteiro> }` quando a quantidade passa do estoque.
- A tela mostra a mensagem `So temos <disponivel> unidades deste item.` (literal) e mantem o carrinho como estava.
- Teste de unidade: `npm test -- <arquivo>`. Nunca apagar dados do banco local.

## FRENTE A: servidor (mestre A)

ESCOPO (so estes): `src/api/carrinho.ts`, `src/api/carrinho.test.ts`, `src/carrinho/adicionar.ts`, `src/carrinho/adicionar.test.ts`.
Estado: `<scratch>/estado-A.md`. Tetos: 3 operarios ao mesmo tempo, 6 despachos.
A1. `adicionarItem` lanca `ESTOQUE_INSUFICIENTE` quando `quantidade existente + pedida > estoque` (limite exato passa).
A2. A rota `POST /carrinho/itens` traduz o erro no `409` do contrato.
Casos: estoque 5 + pedir 5 = 200; estoque 5, ja 3, pedir 3 = 409 com `disponivel: 2`; estoque 0 = 409 com `disponivel: 0`.
ACEITE A: `npm test -- src/api/carrinho.test.ts src/carrinho/adicionar.test.ts` passa; desfazer A1 derruba pelo menos 2 testes.

## FRENTE B: tela (mestre B, MESTRE DA ENTREGA)

ESCOPO (so estes): `src/telas/Carrinho.tsx`, `src/telas/Carrinho.test.tsx`, `src/telas/mensagens.ts`.
Estado: `<scratch>/estado-B.md`. Tetos: 3 operarios ao mesmo tempo, 6 despachos.
B1. Ao receber `409` com `ESTOQUE_INSUFICIENTE`, mostrar a mensagem literal do contrato com o numero de `disponivel`.
B2. Manter a lista de itens como estava antes do clique.
Casos: `disponivel: 2` -> "So temos 2 unidades deste item."; `disponivel: 0` -> "So temos 0 unidades deste item."; resposta 500 -> mensagem generica que ja existe.
ACEITE B: `npm test -- src/telas/Carrinho.test.tsx` passa; abrir a tela com a API falsa devolvendo 409 e ver a mensagem (print).

## ACEITE GLOBAL (mestre B roda no fim)

1. Sobe a API local e a tela; adiciona 6 unidades de um item com estoque 5; a tela mostra "So temos 5 unidades deste item.".
2. Mestre B revisa a COSTURA: o corpo do `409` que a frente A produz e exatamente o que a frente B le (`erro` e `disponivel`).

## Regras para os mestres

- Planta fechada: duvida de contrato volta em `FALTA_DECISAO`, todas juntas, numa chamada so; duvida que e so da frente, decida e anote.
- `model` explicito em toda chamada de operario; briefs nivel 3 pra tudo que escreve, com as decisoes acima coladas LITERAIS.
