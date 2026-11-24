# -*- coding: utf-8 -*-
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(AQUI), "custo.py")
sys.path.insert(0, os.path.dirname(AQUI))
import custo  # noqa: E402

SID = "sessao-ficticia-0001"


def linha(mid, out=100, model="claude-haiku-4-5", inp=0, cr=0, cw=0, cc=None, side=False):
    u = {"input_tokens": inp, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw, "output_tokens": out}
    if cc is not None:
        u["cache_creation"] = cc
    o = {"type": "assistant", "message": {"id": mid, "model": model, "usage": u}}
    if side:
        o["isSidechain"] = True
    return o


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orqcusto_")
        self.projects = os.path.join(self.tmp, "projects")
        self.registro = os.path.join(self.tmp, "reg", "registro.jsonl")
        self.escopo = os.path.join(self.projects, "esc")
        os.makedirs(custo._long(self.escopo))
        self.env = dict(os.environ)
        self.env["ORQ_PROJECTS"] = self.projects
        self.env["ORQ_REGISTRO"] = self.registro
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        self.env.pop("ORQ_PRECOS", None)

    def tearDown(self):
        shutil.rmtree(custo._long(self.tmp), ignore_errors=True)

    def escreve(self, caminho, linhas):
        os.makedirs(custo._long(os.path.dirname(caminho)), exist_ok=True)
        with open(custo._long(caminho), "w", encoding="utf-8") as fh:
            for l in linhas:
                fh.write((l if isinstance(l, str) else json.dumps(l)) + "\n")

    def agente(self, linhas, meta=None, escopo=None, sid=SID, nome="agent-x1", sub=""):
        base = os.path.join(escopo or self.escopo, sid, "subagents", sub) if sub else os.path.join(escopo or self.escopo, sid, "subagents")
        p = os.path.join(base, nome + ".jsonl")
        if linhas is not None:
            self.escreve(p, linhas)
        if meta is not None:
            os.makedirs(custo._long(base), exist_ok=True)
            with open(custo._long(os.path.join(base, nome + ".meta.json")), "w", encoding="utf-8") as fh:
                json.dump(meta, fh)
        return p

    def run_c(self, *args):
        return subprocess.run([sys.executable, SCRIPT] + list(args), env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def js(self, *args):
        r = self.run_c(*args, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)


class TestCusto(Base):
    def test_dedupe(self):
        self.agente([linha("m1"), linha("m1")], {"agentType": "orq-leitor", "description": "d"})
        d = self.js("--sessao", SID)
        self.assertEqual(d["agentes"][0]["respostas"], 1)
        self.assertEqual(d["agentes"][0]["saida"], 100)

    def test_maior_output(self):
        self.agente([linha("m1", out=10), linha("m1", out=50)])
        d = self.js("--sessao", SID)
        self.assertEqual(d["agentes"][0]["saida"], 50)

    def test_synthetic(self):
        self.agente([linha("m1", model="<synthetic>"), linha("m2")])
        d = self.js("--sessao", SID)
        self.assertEqual(d["agentes"][0]["respostas"], 1)

    def test_caminho_longo(self):
        esc = os.path.join(self.projects, "e" * 180)
        self.agente([linha("m1")], {"agentType": "x"}, escopo=esc, nome="agent-" + "z" * 40, sub="workflows")
        self.assertGreater(len(os.path.join(esc, SID, "subagents", "workflows", "agent-" + "z" * 40 + ".jsonl")), 260)
        d = self.js("--sessao", SID)
        self.assertEqual(d["total"]["agentes"], 1)

    def test_pesos(self):
        self.agente([linha("m1", inp=1000, out=100, model="claude-haiku-4-5")], nome="agent-h")
        self.agente([linha("m2", inp=1000, out=100, model="claude-opus-5-5")], nome="agent-o")
        d = self.js("--sessao", SID)
        por = {a["modelo"]: a["custo"] for a in d["agentes"]}
        for f in ("claude-haiku-4-5", "claude-opus-5-5"):
            peso = custo.PRECO[f]["entrada"] / custo.PRECO[custo.UNIDADE]["entrada"]
            r = custo.PRECO[f]["saida"] / custo.PRECO[f]["entrada"]
            self.assertAlmostEqual(por[f], peso * (1000 + r * 100), places=6)

    def test_1h(self):
        self.agente([linha("m1", cw=1000, cc={"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 1000}, out=0, model="claude-sonnet-5-5")])
        d = self.js("--sessao", SID)
        peso = custo.PRECO["claude-sonnet-5-5"]["entrada"] / custo.PRECO[custo.UNIDADE]["entrada"]
        self.assertAlmostEqual(d["por_componente"]["escrita_cache"]["custo"], peso * 2.0 * 1000, places=6)
        self.assertEqual(d["agentes"][0]["escrita_cache_1h"], 1000)

    def test_chefe(self):
        self.escreve(os.path.join(self.escopo, SID + ".jsonl"),
                     [linha("m1", out=10), linha("m2", out=999, side=True), "lixo nao json"])
        d = self.js("--sessao", SID)
        a = d["agentes"][0]
        self.assertEqual((a["papel"], a["nivel"], a["respostas"], a["saida"]), ("chefe", 0, 1, 10))
        self.assertTrue(a["descricao"].startswith("chefe da sessao sessao-f"))

    def test_sem_jsonl(self):
        self.agente(None, {"agentType": "x"}, nome="agent-solto")
        d = self.js("--sessao", SID)
        self.assertEqual(d["sem_transcript"], 1)
        self.assertEqual(d["total"]["agentes"], 0)

    def test_registro(self):
        self.escreve(self.registro, [{"sessao": "s1"}, "lixo", {"sessao": "s2"}, {"sessao": "s1"}, {"sessao": ""}])
        d = self.js("--do-registro")
        self.assertEqual(d["sessoes"], ["s1", "s2"])

    def test_desconhecido(self):
        self.agente([linha("m1", model="claude-xyz")])
        d = self.js("--sessao", SID)
        self.assertEqual(d["agentes"][0]["familia"], "outro")
        self.assertTrue(d["agentes"][0]["estimado"])

    def test_sem_sessao(self):
        r = self.run_c()
        self.assertEqual(r.returncode, 2)
        self.assertIn("sem sessao", r.stderr)

    def test_simulacao(self):
        self.agente([linha("m1", cr=50000, out=0), linha("m2", cr=50000, out=0)])
        d = self.js("--sessao", SID)
        h = "claude-haiku-4-5"
        base = 2 * custo.custo(h, 0, 50000, 0, 0, 0)["custo"]
        esperado = 2 * custo.custo(h, 0, 30000, 0, 0, 0)["custo"]
        self.assertAlmostEqual(d["total"]["custo"], base, places=6)
        self.assertAlmostEqual(d["simulacao"]["contexto_inicial_menos_20k"]["custo"], esperado, places=6)
        self.assertAlmostEqual(d["simulacao"]["respostas_menos_20"]["custo"], base * 0.8, places=6)

    def test_c8_respostas_menos_20_reduz_tambem_a_saida(self):
        self.agente([linha("m1", cr=50000, out=2000), linha("m2", cr=50000, out=2000)])
        d = self.js("--sessao", SID)
        h = "claude-haiku-4-5"
        base = 2 * custo.custo(h, 0, 50000, 0, 0, 2000)["custo"]
        self.assertAlmostEqual(d["total"]["custo"], base, places=6)
        self.assertAlmostEqual(d["simulacao"]["respostas_menos_20"]["custo"], base * 0.8, places=6)
        # contexto_inicial_menos_20k nao mexe na saida
        esperado = 2 * custo.custo(h, 0, 30000, 0, 0, 2000)["custo"]
        self.assertAlmostEqual(d["simulacao"]["contexto_inicial_menos_20k"]["custo"], esperado, places=6)

    def test_prefixo_maior(self):
        self.assertEqual(custo.chave_preco("claude-opus-5-5"), ("claude-opus-5-5", False))
        self.assertEqual(custo.chave_preco("claude-opus-5"), ("claude-opus-5", False))
        self.assertEqual(custo.chave_preco("claude-opus-5-5-xyz"), ("claude-opus-5-5", False))

    def test_familia_sem_versao(self):
        self.assertEqual(custo.chave_preco("claude-haiku-9-9"), ("claude-haiku-5-5", True))
        self.assertEqual(custo.chave_preco("claude-xyz"), (custo.CHAVE_FALLBACK, True))

    def test_faixa_100k(self):
        self.agente([linha("m1", cr=50000, out=100, model="claude-haiku-5-5"),
                     linha("m2", cr=150000, out=100, model="claude-haiku-5-5")])
        d = self.js("--sessao", SID)
        p = custo.PRECO["claude-haiku-5-5"]
        u = p["entrada"]
        c1 = (u / u) * (0.10 * 50000 + (p["saida"] / p["entrada"]) * 100)
        pe, ps = p["acima_100k"]["entrada"], p["acima_100k"]["saida"]
        c2 = (pe / u) * (0.10 * 150000 + (ps / pe) * 100)
        self.assertAlmostEqual(d["agentes"][0]["custo"], c1 + c2, places=6)

    def test_leitura_por_modelo(self):
        self.agente([linha("m1", cr=1000, out=0, model="claude-opus-5-5")])
        d = self.js("--sessao", SID)
        self.assertAlmostEqual(d["por_componente"]["leitura_cache"]["custo"], (4.0 / 0.10) * 0.05 * 1000, places=6)

    def test_dois_escopos(self):
        for e in ("a", "b"):
            esc = os.path.join(self.projects, e)
            self.escreve(os.path.join(esc, SID + ".jsonl"), [linha("c1")])
            self.agente([linha("m1")], {"agentType": "x"}, escopo=esc, nome="agent-1")
        d = self.js("--sessao", SID)
        self.assertEqual(d["total"]["agentes"], 2)

    def test_spill_20k(self):
        self.agente([linha("m1", inp=8000, cr=5000, cw=10000, out=0)])
        d = self.js("--sessao", SID)
        esperado = custo.custo("claude-haiku-4-5", 3000, 0, 0, 0, 0)["custo"]
        self.assertAlmostEqual(d["simulacao"]["contexto_inicial_menos_20k"]["custo"], esperado, places=6)

    def test_top_invalido(self):
        r = self.run_c("--sessao", SID, "--top", "0")
        self.assertEqual(r.returncode, 2)

    def test_buckets(self):
        self.agente([linha("m1")], {"agentType": "Explore", "spawnDepth": 3})
        self.agente([linha("m2")], {"agentType": "orq-leitor", "spawnDepth": -2}, nome="agent-n")
        d = self.js("--sessao", SID)
        self.assertEqual(d["por_papel"]["outros"]["agentes"], 1)
        self.assertEqual(d["por_nivel"]["3+"]["agentes"], 1)
        self.assertEqual(d["por_nivel"]["1"]["agentes"], 1)

    def test_papel_com_prefixo_de_plugin(self):
        self.agente([linha("m1")], {"agentType": "orquestrador:orq-revisor", "spawnDepth": 1})
        d = self.js("--sessao", SID)
        self.assertEqual(d["por_papel"]["orq-revisor"]["agentes"], 1)
        self.assertEqual(d["por_papel"]["outros"]["agentes"], 0)

    def test_designer_e_engenheiro_tem_papel_proprio(self):
        self.agente([linha("m1")], {"agentType": "orquestrador:orq-designer", "spawnDepth": 1})
        self.agente([linha("m2")], {"agentType": "orq-engenheiro", "spawnDepth": 1}, nome="agent-e")
        d = self.js("--sessao", SID)
        self.assertEqual(d["por_papel"]["orq-designer"]["agentes"], 1)
        self.assertEqual(d["por_papel"]["orq-engenheiro"]["agentes"], 1)
        self.assertEqual(d["por_papel"]["outros"]["agentes"], 0)


class TestPrecos(Base):
    def arq(self, conteudo, nome="precos.json"):
        p = os.path.join(self.tmp, nome)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(conteudo if isinstance(conteudo, str) else json.dumps(conteudo))
        return p

    def mostra(self, *args):
        r = self.run_c(*args, "--mostrar-precos")
        return r

    def test_01_mostrar(self):
        r = self.mostra()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["claude-haiku-5-5"]["entrada"], 0.1)

    def test_02_acrescenta(self):
        p = self.arq({"claude-teste-9": {"entrada": 3, "saida": 15, "leitura": 0.1}})
        r = self.mostra("--precos", p)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        self.assertIn("claude-teste-9", d)
        self.assertIn("claude-haiku-5-5", d)

    def test_03_sobrescreve(self):
        p = self.arq({"claude-haiku-5-5": {"entrada": 0.2, "saida": 1, "leitura": 0.1}})
        r = self.mostra("--precos", p)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["claude-haiku-5-5"]["entrada"], 0.2)

    def test_04_nao_existe(self):
        r = self.mostra("--precos", os.path.join(self.tmp, "nao-existe.json"))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.startswith("precos invalido:"), r.stderr)

    def test_05_topo_lista(self):
        r = self.mostra("--precos", self.arq("[1,2]"))
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stderr.startswith("precos invalido:"), r.stderr)

    def test_06_negativo(self):
        r = self.mostra("--precos", self.arq({"x": {"entrada": -1, "saida": 1, "leitura": 0}}))
        self.assertEqual(r.returncode, 2)
        self.assertIn("x", r.stderr)

    def test_07_bool(self):
        r = self.mostra("--precos", self.arq({"x": {"entrada": True, "saida": 1, "leitura": 0}}))
        self.assertEqual(r.returncode, 2)

    def test_08_sem_leitura(self):
        r = self.mostra("--precos", self.arq({"x": {"entrada": 1, "saida": 1}}))
        self.assertEqual(r.returncode, 2)

    def test_09_chave_estranha(self):
        r = self.mostra("--precos", self.arq({"x": {"entrada": 1, "saida": 1, "leitura": 0, "foo": 1}}))
        self.assertEqual(r.returncode, 2)

    def test_10_env(self):
        p = self.arq({"claude-teste-9": {"entrada": 3, "saida": 15, "leitura": 0.1}})
        self.env["ORQ_PRECOS"] = p
        r = self.mostra()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("claude-teste-9", json.loads(r.stdout))

    def _sessao(self):
        self.agente([linha("m1", model="claude-teste-9-xyz", inp=1000)], {"agentType": "orq-leitor"})
        return self.arq({"claude-teste-9": {"entrada": 3, "saida": 15, "leitura": 0.1}})

    def test_11_json_precos(self):
        p = self._sessao()
        d = self.js("--precos", p, "--sessao", SID)
        self.assertEqual(d["precos"]["sobrescritos"], ["claude-teste-9"])
        self.assertTrue(d["precos"]["arquivo"].endswith("precos.json"))
        self.assertEqual(d["precos"]["lido_em"], custo.PRECO_LIDO_EM)

    def test_12_texto_sem_arquivo(self):
        self._sessao()
        r = self.run_c("--sessao", SID)
        self.assertEqual(r.returncode, 0, r.stderr)
        ultima = r.stdout.strip().splitlines()[-1]
        self.assertTrue(ultima.startswith("precos: tabela interna lida em 2026-11-16"), ultima)

    def test_13_texto_com_arquivo(self):
        p = self._sessao()
        r = self.run_c("--precos", p, "--sessao", SID)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("+ 1 modelo de", r.stdout.strip().splitlines()[-1])

    def test_14_acima_100k(self):
        p = self.arq({"Claude-Z": {"entrada": 1, "saida": 2, "leitura": 0, "acima_100k": {"entrada": 3, "saida": 4}}})
        d, erro = custo.carregar_precos(p)
        self.assertIsNone(erro)
        self.assertEqual(d["claude-z"]["acima_100k"], {"entrada": 3, "saida": 4})

    def test_15_infinito_e_nan_recusados(self):
        for ruim in ("Infinity", "NaN", "-Infinity"):
            with self.subTest(valor=ruim):
                p = os.path.join(self.tmp, "ruim.json")
                with open(p, "w", encoding="utf-8") as f:
                    f.write('{"x": {"entrada": %s, "saida": 1, "leitura": 0}}' % ruim)
                d, erro = custo.carregar_precos(p)
                self.assertIsNone(d)
                self.assertTrue(erro.startswith("precos invalido:"), erro)


if __name__ == "__main__":
    unittest.main()
