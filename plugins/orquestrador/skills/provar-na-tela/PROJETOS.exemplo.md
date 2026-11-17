Copie este arquivo para PROJETOS.md nesta pasta e preencha com os seus projetos.

Uma linha por projeto, com os 8 itens da ficha "Rodar, entrar e conferir a tela". As duas linhas abaixo sao ficticias.

| projeto | como subir | portas | banco local | como entrar | usuario de teste | como conferir a tela | como provar que subiu | gotchas |
|---|---|---|---|---|---|---|---|---|
| loja-exemplo | `npm run dev` na raiz (web e api juntos) | web 5173, api 3001 | `docker compose up -d db` e `npm run seed` | tela /login | usuario `teste` / senha da variavel `SEED_SENHA` (defina um valor descartavel antes do seed) | abrir /catalogo e /carrinho; abrir o modal "Adicionar item"; repetir em 375 px | `GET /health` devolve `versao` igual ao commit | o carrinho so aparece com pelo menos 1 item semeado |
| painel-exemplo | `pnpm --filter web dev` | web 4200 | nenhum (API falsa em `mocks/`) | sem login em modo mock | nenhum | abrir /resumo com tema claro e escuro; abrir a lista suspensa de periodo | `meta name="build"` no HTML servido muda a cada build | o grafico so renderiza com viewport de 1024 px ou mais |
