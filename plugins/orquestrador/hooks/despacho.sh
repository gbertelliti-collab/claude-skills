#!/bin/sh
# Hook do plugin orquestrador que roda antes de o chefe abrir um agente (PreToolUse da ferramenta Agent).
# Quando o despacho e de um operario da skill e foge das regras (sem model, sem [modelo:tipo],
# brief sem ACEITE, modelo maior em execucao), devolve um aviso curto ao chefe.
# So avisa: nunca bloqueia o despacho, nunca falha e nunca faz barulho.
# Qualquer outro uso do Agent sai daqui sem nem chamar o Python.
# So le o registro; grava apenas a memoria de "ja avisei" ao lado dele. Nao usa a rede.

# $0 chega sempre como <raiz do plugin>/hooks/<script>: cortar na ultima barra normal.
case "$0" in
  */*) dir="${0%/*}" ;;
  *) dir="." ;;
esac
motor="$dir/../skills/orquestrador/operarios.py"

entrada=$(cat)

# Despacho da skill tem papel orq-* ou descricao comecando com [modelo:tipo]. Sem nenhum dos
# dois sinais no texto, nao ha o que avaliar.
case "$entrada" in
  *orq-*) ;;
  *'"description"'*'['*':'*']'*) ;;
  *) exit 0 ;;
esac

for py in python3 python "py -3"; do
  if saida=$(printf '%s' "$entrada" | $py "$motor" despacho --hook 2>/dev/null); then
    # so repassa o JSON do motor: frase de um interpretador falso nao vira contexto do chefe
    case "$saida" in
      '{'*) printf '%s\n' "$saida" ;;
    esac
    exit 0
  fi
done
exit 0
