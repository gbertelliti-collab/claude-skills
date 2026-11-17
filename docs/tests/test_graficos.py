# -*- coding: utf-8 -*-
"""Testes do gerador de imagens e do --conferir (docs/graficos.py)."""
import io
import json
import os
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

DOCS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(DOCS)
sys.path.insert(0, DOCS)
import graficos  # noqa: E402
import readme_blocos as rb  # noqa: E402


def dados():
    with io.open(os.path.join(DOCS, "uso-real.json"), encoding="utf-8") as f:
        return json.load(f)


class Imagens(unittest.TestCase):
    def test_sai_uma_imagem_por_idioma_tema_e_largura(self):
        imagens = graficos.gerar_imagens(dados())
        self.assertEqual(len(imagens), len(rb.IMAGENS) * 2 * 2 * 2)
        for nome in rb.IMAGENS:
            for caminho in ("docs/img/%s-claro.svg", "docs/img/%s-escuro-estreito.svg",
                            "docs/img/en/%s-escuro.svg", "docs/img/en/%s-claro-estreito.svg"):
                self.assertIn(caminho % nome, imagens)

    def test_todo_svg_e_xml_valido_e_tem_titulo(self):
        for caminho, conteudo in graficos.gerar_imagens(dados()).items():
            raiz = ET.fromstring(conteudo.encode("utf-8"))
            titulo = raiz.find("{http://www.w3.org/2000/svg}title")
            self.assertTrue(titulo is not None and titulo.text, caminho)

    def test_largura_da_versao_estreita(self):
        for caminho, conteudo in graficos.gerar_imagens(dados()).items():
            esperado = graficos.ESTREITO if caminho.endswith("-estreito.svg") else graficos.LARGO
            self.assertIn('viewBox="0 0 %d ' % esperado, conteudo, caminho)

    def test_ingles_nao_sai_com_texto_em_portugues(self):
        for caminho, conteudo in graficos.gerar_imagens(dados()).items():
            if "/en/" in caminho:
                for palavra in ("tarefas", "chefe", "agentes", "revisão", "de primeira"):
                    self.assertNotIn(palavra, conteudo, caminho)

    def test_poucos_dados_nao_quebra(self):
        d = dados()
        d["por_tipo"] = d["por_tipo"][:1]
        d["custo"]["por_modelo"] = {"sonnet": d["custo"]["por_modelo"]["sonnet"]}
        self.assertEqual(len(graficos.gerar_imagens(d)), 48)

    def test_registro_so_com_tarefa_de_primeira_nao_quebra(self):
        # quem acabou de instalar: nenhuma corrigida, nenhuma falha, nenhum tipo
        d = dados()
        d["resultado"] = {"de_primeira": d["tarefas"]}
        self.assertEqual(len(graficos.gerar_imagens(d)), 48)
        for idioma in ("pt", "en"):
            self.assertEqual(sorted(rb.blocos(d, idioma, {})), sorted(rb.NOMES))
        d["por_tipo"] = []
        self.assertEqual(len(graficos.gerar_imagens(d)), 48)
        rb.blocos(d, "pt", {})


class Conferir(unittest.TestCase):
    def test_repositorio_esta_em_dia(self):
        self.assertEqual(graficos.conferir(dados()), [])

    def test_numero_diferente_no_json_e_acusado(self):
        d = dados()
        d["tarefas"] += 1
        fora = graficos.conferir(d)
        self.assertTrue(any("numeros" in linha for linha in fora), fora)

    def test_linha_de_comando_sai_zero(self):
        r = subprocess.run([sys.executable, os.path.join(DOCS, "graficos.py"), "--conferir"],
                           capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
