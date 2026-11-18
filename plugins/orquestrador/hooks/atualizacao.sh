#!/bin/sh
# Hook de inicio de sessao do plugin orquestrador (sessao nova).
# Se o plugin veio de um marketplace que esta com a atualizacao automatica desligada (o padrao do
# Claude Code pra marketplace de terceiro), devolve UMA linha pedindo ao Claude que avise o usuario
# e pergunte se ele quer ligar. No maximo 1 vez por semana e 3 vezes no total; nunca liga sozinho.
# Nunca falha e nunca faz barulho: sem Python 3, sem marketplace ou ja ligada, sai calado.
# So le arquivos locais de configuracao e grava a data do aviso; nao usa a rede.

# $0 chega sempre como <raiz do plugin>/hooks/<script>: cortar na ultima barra normal.
# (um padrao com barra invertida entre colchetes nao fecha em sh POSIX e nao corta nada)
case "$0" in
  */*) dir="${0%/*}" ;;
  *) dir="." ;;
esac
motor="$dir/../skills/orquestrador/operarios.py"

for py in python3 python "py -3"; do
  if saida=$($py "$motor" atualizacao --hook 2>/dev/null </dev/null); then
    if [ -n "$saida" ]; then
      printf '%s\n' "$saida"
    fi
    exit 0
  fi
done
exit 0
