# -*- coding: utf-8 -*-
"""Testes de ESTRUTURA do plugin orquestrador (sem chamar modelo).

Roda com: py -3 -m unittest discover -s docs/tests -p "test_estrutura_plugin.py" -v
"""
import io
import json
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLUGIN = os.path.join(RAIZ, "plugins", "orquestrador")

SKILLS = {"orquestrador", "auditoria-adversarial", "provar-na-tela", "bater-valores", "placar"}
AGENTES = {"orq-leitor", "orq-executor", "orq-revisor", "orq-mestre", "orq-engenheiro"}
MODELOS = {"haiku", "sonnet", "opus", "fable"}
CORES = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
EVENTOS = {
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse", "PostToolUse",
    "SubagentStart", "SubagentStop", "Stop", "PreCompact", "PostCompact", "Notification",
}
CHAVES_PROIBIDAS_AGENTE = ["permissionMode", "hooks", "mcpServers", "initialPrompt"]


def ler(caminho):
    with io.open(caminho, "rb") as f:
        return f.read().decode("utf-8")


def ler_bytes(caminho):
    with io.open(caminho, "rb") as f:
        return f.read()


def frontmatter(texto):
    texto = texto.replace("\r\n", "\n")
    if not texto.startswith("---"):
        raise AssertionError("arquivo nao comeca com frontmatter (---)")
    linhas = texto.split("\n")
    dados = {}
    fechou = False
    for linha in linhas[1:]:
        if linha == "---":
            fechou = True
            break
        if ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == '"' and valor[-1] == '"':
            valor = valor[1:-1]
        dados[chave.strip()] = valor
    if not fechou:
        raise AssertionError("frontmatter sem a linha de fechamento (---)")
    return dados


def carregar_plugin():
    return json.loads(ler(os.path.join(PLUGIN, ".claude-plugin", "plugin.json")))


def carregar_marketplace():
    return json.loads(ler(os.path.join(RAIZ, ".claude-plugin", "marketplace.json")))


def carregar_hooks():
    return json.loads(ler(os.path.join(PLUGIN, "hooks", "hooks.json")))


def arquivos_skill():
    """Mapa nome_da_pasta -> caminho do SKILL.md."""
    pasta = os.path.join(PLUGIN, "skills")
    mapa = {}
    for nome in os.listdir(pasta):
        caminho = os.path.join(pasta, nome, "SKILL.md")
        if os.path.isfile(caminho):
            mapa[nome] = caminho
    return mapa


def arquivos_agente():
    """Mapa nome_sem_md -> caminho do arquivo .md em agents/."""
    pasta = os.path.join(PLUGIN, "agents")
    mapa = {}
    for nome in os.listdir(pasta):
        if nome.endswith(".md"):
            mapa[nome[:-3]] = os.path.join(pasta, nome)
    return mapa


class TestEstrutura(unittest.TestCase):

    def test_01_marketplace(self):
        m = carregar_marketplace()
        self.assertEqual(m.get("name"), "gbertelli-skills")
        owner = m.get("owner")
        self.assertIsInstance(owner, dict, "owner deve ser objeto")
        self.assertIsInstance(owner.get("name"), str)
        self.assertTrue(owner.get("name"), "owner.name vazio")
        plugins = m.get("plugins")
        self.assertIsInstance(plugins, list, "plugins deve ser lista")
        self.assertEqual(len(plugins), 1, "plugins deve ter exatamente 1 item")
        item = plugins[0]
        self.assertEqual(item.get("name"), "orquestrador")
        self.assertEqual(item.get("source"), "./plugins/orquestrador")
        pasta = os.path.normpath(os.path.join(RAIZ, item["source"]))
        self.assertTrue(os.path.isdir(pasta), "pasta do source nao existe: " + pasta)

    def test_02_plugin_json(self):
        p = carregar_plugin()
        self.assertEqual(p.get("name"), "orquestrador")
        self.assertEqual(p.get("license"), "MIT")
        self.assertIsInstance(p.get("description"), str)
        self.assertTrue(p.get("description"), "description vazia")

    def test_03_sem_version(self):
        msg = "sem version de proposito: cada commit chega em quem instalou"
        self.assertNotIn("version", carregar_plugin(), msg)
        for item in carregar_marketplace()["plugins"]:
            self.assertNotIn("version", item, msg)

    def test_04_homepage_repository_keywords(self):
        p = carregar_plugin()
        for chave in ("homepage", "repository"):
            valor = p.get(chave)
            self.assertIsInstance(valor, str, chave + " deve ser string")
            self.assertTrue(valor.startswith("https://"), chave + " deve comecar com https://")
        keywords = p.get("keywords")
        self.assertIsInstance(keywords, list, "keywords deve ser lista")
        self.assertTrue(len(keywords) > 0, "keywords vazia")
        for k in keywords:
            self.assertIsInstance(k, str)
            self.assertTrue(k.strip(), "keyword vazia")

    def test_05_conjunto_de_skills(self):
        self.assertEqual(set(arquivos_skill().keys()), SKILLS)

    def test_06_frontmatter_skills(self):
        for nome, caminho in sorted(arquivos_skill().items()):
            with self.subTest(skill=nome):
                fm = frontmatter(ler(caminho))
                self.assertEqual(fm.get("name"), nome)
                self.assertTrue(fm.get("description"), "description vazia")

    def test_07_disable_model_invocation(self):
        for nome, caminho in sorted(arquivos_skill().items()):
            with self.subTest(skill=nome):
                fm = frontmatter(ler(caminho))
                if nome == "placar":
                    self.assertEqual(fm.get("disable-model-invocation"), "true")
                else:
                    self.assertNotIn("disable-model-invocation", fm)

    def test_08_conjunto_de_agentes(self):
        self.assertEqual(set(arquivos_agente().keys()), AGENTES)

    def test_09_frontmatter_agentes(self):
        for nome, caminho in sorted(arquivos_agente().items()):
            with self.subTest(agente=nome):
                fm = frontmatter(ler(caminho))
                self.assertEqual(fm.get("name"), nome)
                self.assertTrue(fm.get("description"), "description vazia")
                self.assertIn(fm.get("model"), MODELOS)
                self.assertIn(fm.get("color"), CORES)

    def test_10_chaves_proibidas_em_agente(self):
        for nome, caminho in sorted(arquivos_agente().items()):
            with self.subTest(agente=nome):
                fm = frontmatter(ler(caminho))
                for chave in CHAVES_PROIBIDAS_AGENTE:
                    self.assertNotIn(chave, fm, "chave ignorada pelo Claude Code em agente de plugin: " + chave)

    def test_11_hooks_json(self):
        hj = carregar_hooks()
        self.assertIsInstance(hj, dict)
        self.assertIn("hooks", hj)
        self.assertIsInstance(hj["hooks"], dict, "hooks deve ser objeto")
        for evento, itens in hj["hooks"].items():
            with self.subTest(evento=evento):
                self.assertIn(evento, EVENTOS, "evento desconhecido: " + evento)
                self.assertIsInstance(itens, list)
                for item in itens:
                    self.assertIsInstance(item.get("hooks"), list, "item sem lista hooks")
                    for h in item["hooks"]:
                        self.assertEqual(h.get("type"), "command")
                        cmd = h.get("command")
                        self.assertIsInstance(cmd, str)
                        self.assertTrue(cmd.strip(), "command vazio")

    def test_12_caminhos_do_hook_existem(self):
        regex = r'\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+)'
        achados = []
        for itens in carregar_hooks()["hooks"].values():
            for item in itens:
                for h in item.get("hooks", []):
                    achados.extend(re.findall(regex, h.get("command", "")))
        self.assertTrue(achados, "nenhum caminho ${CLAUDE_PLUGIN_ROOT}/ encontrado nos hooks")
        for rel in achados:
            with self.subTest(caminho=rel):
                caminho = os.path.normpath(os.path.join(PLUGIN, *rel.split("/")))
                self.assertTrue(os.path.exists(caminho), "caminho do hook nao existe: " + caminho)

    def test_13_retomar_sh_lf(self):
        data = ler_bytes(os.path.join(PLUGIN, "hooks", "retomar.sh"))
        self.assertTrue(data.startswith(b"#!/bin/sh"), "shebang ausente")
        self.assertNotIn(b"\r", data, "retomar.sh com CR (deve ser LF)")

    def test_13b_hooks_de_inicio(self):
        # um script por evento de inicio: retomada (compactou/retomou) e aviso de atualizacao (sessao nova)
        entradas = carregar_hooks()["hooks"]["SessionStart"]
        mapa = {e.get("matcher"): e["hooks"][0]["command"] for e in entradas}
        self.assertEqual(set(mapa), {"compact|resume", "startup"})
        self.assertIn("hooks/retomar.sh", mapa["compact|resume"])
        self.assertIn("hooks/atualizacao.sh", mapa["startup"])
        for e in entradas:
            self.assertLessEqual(e["hooks"][0].get("timeout", 60), 30, "hook de inicio nao pode segurar a sessao")
        data = ler_bytes(os.path.join(PLUGIN, "hooks", "atualizacao.sh"))
        self.assertTrue(data.startswith(b"#!/bin/sh"), "shebang ausente")
        self.assertNotIn(b"\r", data, "atualizacao.sh com CR (deve ser LF)")
        self.assertIn(b"atualizacao --hook", data)
        self.assertNotIn(b"--ligar", data, "o hook nunca liga sozinho")

    def test_13c_hook_de_despacho(self):
        # antes de abrir um agente: so avisa. O script nunca pode bloquear nem decidir permissao.
        entradas = carregar_hooks()["hooks"]["PreToolUse"]
        self.assertEqual(len(entradas), 1)
        e = entradas[0]
        self.assertEqual(e.get("matcher"), "Agent|Task", "so a ferramenta de abrir agente; nunca Bash, Edit etc.")
        self.assertIn("hooks/despacho.sh", e["hooks"][0]["command"])
        self.assertLessEqual(e["hooks"][0].get("timeout", 60), 15, "hook de despacho nao pode segurar o agente")
        data = ler_bytes(os.path.join(PLUGIN, "hooks", "despacho.sh"))
        self.assertTrue(data.startswith(b"#!/bin/sh"), "shebang ausente")
        self.assertNotIn(b"\r", data, "despacho.sh com CR (deve ser LF)")
        self.assertIn(b"despacho --hook", data)
        for proibido in (b"exit 2", b"permissionDecision", b"deny"):
            self.assertNotIn(proibido, data, "o hook de despacho so avisa")
        # todo caminho de saida do script e exit 0
        saidas = [l.strip() for l in data.decode("ascii").splitlines() if l.strip().startswith("exit ")
                  or " exit " in l]
        self.assertTrue(saidas and all("exit 0" in l for l in saidas), saidas)

    def test_14_ascii_e_caminhos_de_skill(self):
        regex = r'\$\{CLAUDE_SKILL_DIR\}/([A-Za-z0-9_./-]+)'
        arquivos = [(nome, c) for nome, c in arquivos_skill().items()]
        arquivos += [(nome, c) for nome, c in arquivos_agente().items()]
        for nome, caminho in sorted(arquivos):
            with self.subTest(arquivo=caminho):
                data = ler_bytes(caminho)
                nao_ascii = [i for i, b in enumerate(data) if b >= 128]
                self.assertFalse(nao_ascii, "byte nao ASCII no offset %d" % (nao_ascii[0] if nao_ascii else -1))
        for nome, caminho in sorted(arquivos_skill().items()):
            with self.subTest(skill_caminhos=nome):
                pasta = os.path.dirname(caminho)
                for rel in re.findall(regex, ler(caminho)):
                    alvo = os.path.normpath(os.path.join(pasta, *rel.split("/")))
                    self.assertTrue(os.path.exists(alvo), "CLAUDE_SKILL_DIR aponta pra nada: " + alvo)
        orq = arquivos_skill()["orquestrador"]
        linhas = ler(orq).splitlines()
        self.assertLessEqual(len(linhas), 230, "SKILL.md do orquestrador com mais de 230 linhas")

    def test_15_cede_pro_fluxo_do_projeto(self):
        # a skill abre sozinha; quem ja tem fluxo proprio (agente especialista) nao pode ser atropelado
        texto = ler(arquivos_skill()["orquestrador"])
        desc = frontmatter(texto)["description"]
        self.assertIn("Tarefa que o proprio projeto ja entrega a alguem", desc)
        self.assertIn("nao abra esta skill por cima, salvo se o usuario pedir pelo nome", desc)
        self.assertIn("- Fluxo do projeto vence, e so na parte dele.", texto)
        # e nao pode virar freio pra uso comum: a regra normal tem que continuar escrita
        self.assertIn("Usa em TODO trabalho com 2 ou mais partes independentes", desc)
        self.assertIn("Projeto sem dono definido pra tarefa (a maioria) = regra normal, a skill abre sozinha.", texto)
        for nome, caminho in sorted(arquivos_skill().items()):
            with self.subTest(skill=nome):
                d = frontmatter(ler(caminho))["description"]
                self.assertLessEqual(len(d), 1024, "description passa de 1024 caracteres (limite das skills)")
        for readme, frase in (("README.md", "### Se você já tem um fluxo próprio"),
                              ("README.en.md", "### If you already have your own flow")):
            with self.subTest(readme=readme):
                r = ler(os.path.join(RAIZ, readme))
                self.assertIn(frase, r)
                self.assertIn("`Skill(orquestrador:orquestrador)`", r)


if __name__ == "__main__":
    unittest.main()
