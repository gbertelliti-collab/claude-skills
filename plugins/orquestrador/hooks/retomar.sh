#!/bin/sh
# Hook de inicio de sessao do plugin orquestrador (depois de compactar ou de retomar).
# Se esta sessao ja despachou operarios, devolve ao chefe quem ficou sem registro.
# Nunca falha e nunca faz barulho: sem Python 3, sem sessao ou sem operarios, sai calado.
# So le: nao grava, nao apaga e nao usa a rede.

case "$0" in
  */*|*\\*) dir="${0%[/\\]*}" ;;
  *) dir="." ;;
esac
motor="$dir/../skills/orquestrador/operarios.py"

entrada=$(cat)

for py in python3 python "py -3"; do
  if saida=$(printf '%s' "$entrada" | $py "$motor" retomar --hook 2>/dev/null); then
    if [ -n "$saida" ]; then
      printf '%s\n' "$saida"
    fi
    exit 0
  fi
done
exit 0
