# Exemplo de brief nivel 2 (leitura) - projeto ficticio "loja-exemplo"

Despacho: papel `orquestrador:orq-leitor`, `model: "haiku"`, `description: "[haiku:leitura] onde o carrinho calcula o total"`.

```
OBJETIVO: dizer em que arquivos e funcoes o total do carrinho e calculado e quais telas usam esse total.

ESCOPO: so leitura. Pasta `src/` do projeto. Nao edite nada, nao grave arquivo.

FONTES:
- `rg -n "total" src/carrinho src/servicos` (comece por aqui)
- `rg -n "calcularTotal|totalDoCarrinho" src` (quem chama)
- testes: `src/carrinho/*.test.ts`

CONTEXTO:
- O carrinho guarda itens com `precoUnitario` e `quantidade`.
- Premissa do chefe, a CONFIRMAR: existe uma unica funcao `calcularTotal` em `src/carrinho/total.ts`. Se voce nao achar, diga "o brief diz X e eu nao achei".
- Ja se sabe que o desconto fica em outro modulo (`src/promocoes`); nao precisa ler ele.

RESTRICOES:
- Nao investigue fora de `src/carrinho`, `src/servicos` e as telas que chamam o total.
- Codigo e numero de linha voce COPIA da saida da ferramenta; nunca redigite de memoria.

AVISOS:
- (nenhum ainda para este tipo)

ENTREGA: resumo de ate 15 linhas, nesta ordem:
  STATUS: FEITO | PARCIAL | FALTA_CONTEXTO
  RESPOSTA: lista `arquivo:linha | o que faz` das funcoes que calculam o total; lista das telas que usam
  EVIDENCIA: o comando que rodou para cada item
  NAO VERIFICADO: o que ficou sem prova

ACEITE (o chefe confere): abre 2 dos `arquivo:linha` citados e ve que o trecho existe; roda o `rg` da primeira fonte e confirma que nenhum arquivo de calculo ficou de fora.
```

Por que esse brief funciona: o comando pronto em FONTES, a premissa marcada "a confirmar", o formato exato da ENTREGA e um ACEITE que o chefe consegue rodar em 1 comando.
