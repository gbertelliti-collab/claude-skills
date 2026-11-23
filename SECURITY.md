# Política de segurança

## Versões suportadas

Só a `main` atual recebe correções.

## Como reportar

Use o botão "Report a vulnerability" da aba Security do repositório:
https://github.com/gbertelliti-collab/claude-skills/security/advisories/new

Não abra issue pública para vulnerabilidade.

## O que o plugin faz na sua máquina

- O motor lê os transcripts locais do Claude Code e grava um registro local.
- Ele não envia nada pela rede.
- O registro passa por uma redação de segredos antes de ser gravado.
- Os três hooks do plugin só rodam o próprio motor. O de retomada só lê. O de despacho só avisa: não bloqueia a abertura do agente, não decide permissão, não altera a chamada e não grava o brief; guarda apenas, ao lado do registro, quais avisos já deu na sessão. O de atualização lê a configuração local de plugins do Claude Code e grava a data do último aviso.
- O seu `settings.json` só é alterado pelo comando `atualizacao --ligar`, que o Claude roda depois que você aceita ligar a atualização automática. Ele acrescenta `autoUpdate: true` na entrada do marketplace (e, no app desktop, `FORCE_AUTOUPDATE_PLUGINS=1` em `env`) e guarda uma cópia do arquivo ao lado, em `settings.json.antes-do-orquestrador`.

## Fora do escopo

Falha do Claude Code em si: reporte à Anthropic.
