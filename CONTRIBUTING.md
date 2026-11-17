# Como contribuir

Obrigado por querer ajudar. Este repositório é o plugin `orquestrador` do Claude Code, do marketplace `gbertelli-skills`, e toda melhoria com caso real é bem-vinda.

Repositório: https://github.com/gbertelliti-collab/claude-skills

## Antes de abrir um PR

Testes do motor:

```bash
cd plugins/orquestrador/skills/orquestrador
```

```bash
python -m unittest discover -s tests
```

Testes da estrutura do plugin e do gerador do README (na raiz):

```bash
python -m unittest discover -s docs/tests
```

README em dia com os números (sai 1 se o README ou uma imagem não bate com `docs/uso-real.json`):

```bash
python docs/graficos.py --conferir
```

Os trechos do README entre `<!-- uso-real:NOME:inicio -->` e `<!-- uso-real:NOME:fim -->` são gerados. Não edite à mão: rode `python docs/graficos.py`.

Validar o plugin (1 aviso esperado: "No version specified"):

```bash
claude plugin validate .
```

Testar o plugin sem instalar:

```bash
claude --plugin-dir plugins/orquestrador
```

## Regras do projeto

1. O motor (`operarios.py`, `custo.py`) é Python 3.10+ só com a biblioteca padrão. Sem dependência.
2. O `plugin.json` não tem o campo `version`, de propósito: sem ele cada commit chega em quem instalou. Não adicione.
3. Os arquivos das skills e dos agentes (`SKILL.md`, `agents/*.md`) e o código são escritos sem acento (ASCII). O README e os documentos para gente ler têm acento.
4. Toda regra nova do `SKILL.md` precisa de evidência anotada em `fundamentos.md`: medição, fonte oficial ou relato de uso real, com link.
5. O `SKILL.md` é lido pelo modelo em toda obra, e cada linha custa token. Mudança que aumenta o arquivo precisa justificar.
6. Nada de dado pessoal, nome de cliente, caminho de máquina ou chave em issue, PR ou exemplo.
7. O README existe em português (`README.md`) e inglês (`README.en.md`). Mudou uma frase num, porte para o outro.

## Como propor mudança numa regra da skill

Abra uma issue com o caso real. Diga o que o operário ou o chefe fez de errado.
Anexe a evidência (medição, fonte oficial ou relato com link).

Issues and pull requests in English are welcome.
