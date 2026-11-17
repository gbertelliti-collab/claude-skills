# Exemplo de brief nivel 3 (edicao) - projeto ficticio "loja-exemplo"

Despacho: papel `orquestrador:orq-executor`, `model: "sonnet"`, `description: "[sonnet:edicao-logica] limite de quantidade no carrinho"`.

```
OBJETIVO: impedir que um item entre no carrinho com quantidade maior que o estoque.

ESCOPO (edite SO estes dois arquivos):
- src/carrinho/adicionar.ts
- src/carrinho/adicionar.test.ts

FONTES: `rg -n "adicionarItem" src` (3 usos, todos passam pela funcao abaixo).

CONTEXTO (trecho atual de src/carrinho/adicionar.ts, linhas 12-20):
  export function adicionarItem(carrinho: Carrinho, produto: Produto, quantidade: number): Carrinho {
    const existente = carrinho.itens.find((i) => i.produtoId === produto.id);
    if (existente) {
      existente.quantidade += quantidade;
    } else {
      carrinho.itens.push({ produtoId: produto.id, precoUnitario: produto.preco, quantidade });
    }
    return carrinho;
  }
Decisao do chefe (literal): quando passar do estoque, lance `new Error("ESTOQUE_INSUFICIENTE")`. Nao mude a assinatura. O estoque vem de `produto.estoque` (numero inteiro >= 0).

PASSOS:
1. Calcule `total = (existente ? existente.quantidade : 0) + quantidade`.
2. Se `total > produto.estoque`, lance o erro acima ANTES de alterar o carrinho.
3. Senao, mantenha o comportamento de hoje.
4. Acrescente os casos da tabela em adicionar.test.ts, no mesmo estilo dos testes vizinhos.

CASOS ESPERADOS:
| estoque | ja no carrinho | quantidade pedida | resultado |
|---|---|---|---|
| 5 | 0 | 5 | adiciona (limite exato) |
| 5 | 3 | 3 | lanca ESTOQUE_INSUFICIENTE, carrinho igual ao de antes |
| 0 | 0 | 1 | lanca ESTOQUE_INSUFICIENTE |
| 5 | 0 | 0 | adiciona sem mudar nada (quantidade 0 e aceita) |

NAO FAZER: nao mexa em `src/carrinho/total.ts`; nao crie dependencia nova; nao mude os 3 chamadores (outra tarefa trata a mensagem na tela).
PARE e devolva FALTA_CONTEXTO se `produto.estoque` puder ser nulo no tipo `Produto`.

AVISOS (da ficha, literais):
- cuidado: 2 de 3 entregas com erro foram de borda -> no brief: tabela de casos com vazio, nulo, zero e limite (esta acima).

ENTREGA: resumo de ate 15 linhas: STATUS, ARQUIVOS, ACEITE (comando + ultimas linhas reais), DECISOES, RISCOS.

ACEITE (o chefe roda): `npm test -- src/carrinho/adicionar.test.ts` passa; o chefe desfaz a checagem do passo 2, roda de novo e os 2 casos de erro tem que cair.
```

Por que esse brief funciona: trecho atual colado, decisao literal (nome do erro), tabela de casos com os limites e um ACEITE que consegue falhar.
