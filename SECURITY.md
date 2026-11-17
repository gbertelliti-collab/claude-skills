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
- O hook do plugin só roda o próprio motor, em modo leitura.

## Fora do escopo

Falha do Claude Code em si: reporte à Anthropic.
