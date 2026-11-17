# -*- coding: utf-8 -*-
import io
import json
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(DOCS)
sys.path.insert(0, DOCS)

import readme_blocos as rb  # noqa: E402


def dados_exemplo():
    """Retrato congelado (140 tarefas): os textos EXATOS dos testes saem dele."""
    with io.open(os.path.join(DOCS, "tests", "retrato-exemplo.json"), encoding="utf-8") as f:
        return json.load(f)


def dados_reais():
    with io.open(os.path.join(DOCS, "uso-real.json"), encoding="utf-8") as f:
        return json.load(f)


TIPOS_PT = [
    "- **Ler, pesquisar e revisar:** 75 de 76 tarefas passaram de primeira; o Haiku recebeu 28 delas e passou 28 de primeira.",
    "- **Escrever código (edição lógica e front):** 25 de 46 passaram de primeira; das outras 21, 20 o próprio operário corrigiu e 1 o chefe terminou.",
    "- **No total:** das 25 que não passaram de primeira, 23 o próprio operário corrigiu em até 2 rodadas e 2 o chefe terminou.",
]
CUSTO_PT = [
    "Medição do `custo.py` nas mesmas 4 sessões, inteiras: 346 agentes (os 4 chefes de sessão entram na conta) e 17.515 respostas.",
    "",
    "- **Haiku e Sonnet na conta:** os 130 agentes Haiku e Sonnet são 38% dos agentes e 3,1% do custo.",
    "- **Reler ou escrever:** 78% do custo é reler contexto a cada resposta (46% leitura de cache, 32% escrita de cache); o que os modelos escrevem é 22%.",
    "- **Por papel:** os 4 chefes de sessão ficam com 34%; agentes genéricos (`general-purpose`), 24%; executores `orq-executor`, 21%; revisores `orq-revisor`, 2,6%; mestres `orq-mestre`, 1,1%; leitores `orq-leitor`, 0,2%; agentes de fora do plugin, 18%.",
    "- **Simulação:** 20% menos respostas corta 20% do custo; encolher em 20 mil tokens o contexto inicial de cada agente corta 3,3%.",
]


class Formatos(unittest.TestCase):
    def test_periodo(self):
        casos = [
            ("2026-11-15", "2026-11-17", "entre 15 e 17/11/2026", "between Nov 15 and 17, 2026"),
            ("2026-11-28", "2026-12-03", "entre 28/11/2026 e 03/12/2026", "between Nov 28, 2026 and Dec 3, 2026"),
            ("2026-11-17", "2026-11-17", "em 17/11/2026", "on Nov 17, 2026"),
        ]
        for de, ate, pt, en in casos:
            self.assertEqual(rb.periodo(de, ate, "pt"), pt)
            self.assertEqual(rb.periodo(de, ate, "en"), en)

    def test_pct(self):
        self.assertEqual(rb.pct(33.72), "34")
        self.assertEqual(rb.pct(2.61), "2,6")
        self.assertEqual(rb.pct(0.23), "0,2")
        self.assertEqual(rb.pct(9.96), "10")
        self.assertEqual(rb.pct(2.61, "en"), "2.6")
        self.assertEqual(rb.pct(0.15), "0,2")  # metade pra cima

    def test_mil_milhar(self):
        self.assertEqual(rb.mil(12817), "13 mil")
        self.assertEqual(rb.mil(12817, "en"), "13k")
        self.assertEqual(rb.mil(12500), "13 mil")
        self.assertEqual(rb.milhar(17515), "17.515")
        self.assertEqual(rb.milhar(17515, "en"), "17,515")


class Aplicar(unittest.TestCase):
    TEXTO = "a\n<!-- uso-real:x:inicio -->\n\nvelho\n\n<!-- uso-real:x:fim -->\nb\n"

    def test_idempotente(self):
        t1, f1 = rb.aplicar(self.TEXTO, {"x": "novo\nlinha"})
        self.assertEqual(f1, [])
        self.assertIn("\n\nnovo\nlinha\n\n", t1)
        self.assertNotIn("velho", t1)
        t2, _ = rb.aplicar(t1, {"x": "novo\nlinha"})
        self.assertEqual(t1, t2)

    def test_ausente(self):
        t, falt = rb.aplicar(self.TEXTO, {"y": "z"})
        self.assertEqual(falt, ["y"])
        self.assertEqual(t, self.TEXTO)


class Imagem(unittest.TestCase):
    def test_simples(self):
        s = rb.imagem("numeros", 'a & b <c> "d"')
        self.assertEqual(s.count("<source"), 1)
        self.assertIn('srcset="docs/img/numeros-escuro.svg"', s)
        self.assertIn('alt="a &amp; b &lt;c&gt; &quot;d&quot;"', s)
        self.assertIn('src="docs/img/numeros-claro.svg" width="100%"', s)

    def test_estreito_e_en(self):
        s = rb.imagem("tipos", "t", "en", True)
        self.assertEqual(s.count("<source"), 3)
        a = s.index("(prefers-color-scheme: dark) and (max-width: 600px)")
        b = s.index('media="(prefers-color-scheme: dark)"')
        c = s.index('media="(max-width: 600px)"')
        self.assertTrue(a < b < c)
        self.assertIn("docs/img/en/tipos-escuro-estreito.svg", s)
        self.assertIn("docs/img/en/tipos-claro-estreito.svg", s)
        self.assertIn('src="docs/img/en/tipos-claro.svg"', s)


class Blocos(unittest.TestCase):
    def test_real_pt(self):
        b = rb.blocos(dados_exemplo(), "pt", {})
        self.assertEqual(sorted(b), sorted(rb.NOMES))
        self.assertEqual(len(b), 12)
        self.assertEqual(b["tipos-texto"].split("\n"), TIPOS_PT)
        self.assertEqual(b["custo-texto"].split("\n"), CUSTO_PT)
        self.assertIn("34 dos 346 agentes", b["modo-god-texto"])
        self.assertIn("| Haiku | 32 | 31 (97%) | 4 | 13 mil tokens | 103 mil |", b["modelos"])
        self.assertIn("| revisão | | 30 / 30 | 6 / 6 |", b["tipo-modelo"])

    def test_real_en(self):
        b = rb.blocos(dados_exemplo(), "en", {})
        self.assertEqual(len(b), 12)
        self.assertIn("13k tokens | 103k |", b["modelos"])
        self.assertTrue(b["tipo-modelo"].startswith("| type | Haiku | Sonnet | Opus |"))
        self.assertIn("2.6%", b["custo-texto"])
        self.assertIn("on the second floor", b["modo-god-texto"])
        self.assertIn("- **Overall:** of the 25 that did not pass first time", b["tipos-texto"])

    def test_sintetico_sem_haiku_e_andar_zero(self):
        d = {
            "periodo": {"de": "2026-11-17", "ate": "2026-11-17", "dias": 1},
            "resultado": {"de_primeira": 1, "corrigido": 0, "falhou": 0},
            "rodadas_max": 0,
            "por_modelo": {"sonnet": {"tarefas": 1, "de_primeira": 1, "saida_mediana": 1000,
                                      "contexto_mediano": 2000, "respostas_mediana": 3}},
            "por_tipo": [{"tipo": "leitura", "tarefas": 1, "de_primeira": 1,
                          "por_modelo": {"sonnet": [1, 1]}, "falhou": 0, "corrigido": 0}],
            "custo": {
                "sessoes": 1, "agentes": 2, "respostas": 10,
                "por_modelo": {"sonnet": {"agentes": 2, "respostas": 10, "pct": 100.0}},
                "por_componente": {"entrada": 0, "leitura_cache": 50, "escrita_cache": 30, "saida": 20},
                "por_papel": {"orq-executor": {"agentes": 2, "respostas": 10, "pct": 100.0}},
                "por_andar": {"2": {"agentes": 0, "pct": 0.0}},
                "simulacao": {"respostas_menos_20": 20.0, "contexto_inicial_menos_20k": 3.3},
            },
        }
        b = rb.blocos(d, "pt", {})
        self.assertNotIn("Haiku recebeu", b["tipos-texto"])
        self.assertTrue(b["tipos-texto"].split("\n")[0].endswith("de primeira."))
        self.assertNotIn("Escrever código", b["tipos-texto"])
        self.assertEqual(b["modo-god-texto"], "O retrato atual ainda não tem obra em modo god.")
        self.assertNotIn("chefes", b["custo-texto"])
        self.assertIn("| Sonnet |", b["tipo-modelo"].split("\n")[0])
        self.assertEqual(rb.blocos(d, "en", {})["modo-god-texto"],
                         "The current snapshot has no god mode job yet.")


class Gerar(unittest.TestCase):
    def test_readme_em_dia(self):
        novo, falt = rb.gerar(RAIZ, dados_reais(), "pt", estreito=True)
        self.assertEqual(falt, [])
        with io.open(os.path.join(RAIZ, "README.md"), encoding="utf-8", newline="") as f:
            atual = f.read().replace("\r\n", "\n")
        self.assertEqual(novo, atual)

    def test_titulos_ausentes(self):
        t = rb.titulos_de_arquivos(RAIZ, "en")
        self.assertEqual(sorted(t), sorted(rb.IMAGENS))


if __name__ == "__main__":
    unittest.main()
