# Molde de brief do auditor

Preencha cada <ASSIM> antes de despachar. Papel `orq-executor`; modelo conforme a fase 2 da skill.

```
OBJETIVO: achar o que paga ou perde dinheiro, vaza dado, duplica, falha calada ou derruba producao no territorio <LETRA>-<TERRITORIO>, e provar cada achado.

TERRITORIO: <PASTAS E ARQUIVOS DESTE AUDITOR>
Fora dele nao leia nem reporte. Se o caminho de um achado sai do territorio, anote "cruza com <outra letra>" e pare ali.

FONTES: <COMANDOS: git ls-files <pasta>, onde estao os testes, onde estao os logs ja disponiveis>
Premissas vindas de memoria, todas "confirmar no codigo" antes de usar: <LISTA>

CONTEXTO: <o que o sistema faz neste territorio, o que ja foi dado como saudavel em auditoria anterior (nao re-persiga), padrao pra copiar>

GRAVIDADE:
P0 = paga ou perde dinheiro de verdade, vaza dado de outra empresa, ou derruba a producao.
P1 = numero errado que o usuario usa pra decidir, falha calada, dado duplicado ou sumido, acesso indevido dentro da mesma empresa.
P2 = defeito real com contorno.
P3 = melhoria.

FORMATO DE CADA ACHADO:
- Titulo e gravidade.
- Onde: arquivo:linha.
- Cenario concreto: entrada -> saida errada.
- PROVADO (comando + saida colada) ou LIDO (so li o codigo). Repeticao de chamada: conte as chamadas com um fetch falso. Corrida: segunda conexao segurando trava. Dinheiro: caso no banco descartavel.
- O que derrubaria este achado (config desligada, tela que nao oferece o caminho, guarda em outro lugar).
- Conserto sugerido: RASCUNHO (quem corrigir vai provar).

SECAO OBRIGATORIA "conferi e esta bom": o que voce examinou e nao tem problema, com arquivo:linha e como conferiu. Vazia = relatorio recusado.

RESTRICOES:
- Nao edita codigo do projeto. Escreve so em <PASTA DE RASCUNHO> e no proprio relatorio.
- Nao toca producao. Nao usa credencial real.
- Ambiente descartavel proprio com a sua letra: banco <adv_LETRA>, porta <PORTA>. Derrube tudo ao fim.
- Nao rode a suite inteira; rode so o que prova o achado.

ENTREGA: relatorio completo em <docs/auditoria/AAAA-MM-DD/LETRA-TERRITORIO.md> + resumo de ate 15 linhas (contagem por gravidade, os 3 piores achados, o que ficou sem provar).

ACEITE: <O QUE O CHEFE CONFERE: arquivo existe, todo P0/P1 tem PROVADO ou LIDO marcado, secao "conferi e esta bom" preenchida, nenhum arquivo do projeto alterado (git status --short igual ao de antes do despacho, fora o proprio relatorio em docs/auditoria/)>
```

Como preencher (o chefe):
- <PASTA DE RASCUNHO>: uma pasta temporaria por auditor, FORA do repositorio (ex.: `<pasta temporaria da sessao>/auditoria/rascunho-<LETRA>/`).
- <PORTA>: porta do README do projeto + numero da letra (A=1, B=2...). <adv_LETRA>: banco descartavel com esse nome; projeto sem banco, apague a linha.
- <LISTA> de premissas: o que o pedido do usuario, as notas do projeto e a auditoria anterior dao como certo sobre o territorio.
- Territorio producao: <onde estao os logs> = arquivo de log que o chefe ja baixou; sem arquivo, nao abra o territorio.
