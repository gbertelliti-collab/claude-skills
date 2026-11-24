# -*- coding: utf-8 -*-
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(AQUI), "operarios.py")
sys.path.insert(0, os.path.dirname(AQUI))
import operarios  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="orqtest_")
        self.registro = os.path.join(self.tmp, "reg", "registro.jsonl")
        self.ficha = os.path.join(self.tmp, "ficha.md")
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(self.projects)
        self.env = dict(os.environ)
        self.env["ORQ_REGISTRO"] = self.registro
        self.env["ORQ_FICHA"] = self.ficha
        self.env["ORQ_PROJECTS"] = self.projects
        self.env["PYTHONIOENCODING"] = "utf-8"
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)

    def tearDown(self):
        shutil.rmtree(operarios._long(self.tmp), ignore_errors=True)

    def run_op(self, *args):
        return subprocess.run([sys.executable, SCRIPT] + list(args), env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def reg(self, tipo, modelo, resultado, rodadas=0, brief=2, erros=(), licao=None):
        a = ["registrar", "--tipo", tipo, "--modelo", modelo, "--resultado", resultado,
             "--rodadas", str(rodadas), "--brief", str(brief)]
        for e in erros:
            a += ["--erro", e]
        if licao:
            a += ["--licao", licao]
        p = self.run_op(*a)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def grava(self, tipo, modelo, resultado, n=1, brief=2, dias=0, **extra):
        """Grava n registros direto no arquivo (permite ts antigo)."""
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        ts = (datetime.now().astimezone() - timedelta(days=dias)).isoformat(timespec="seconds")
        with io.open(self.registro, "a", encoding="utf-8", newline="") as f:
            for _ in range(n):
                d = {"ts": ts, "tipo": tipo, "modelo": modelo, "resultado": resultado,
                     "rodadas": 0 if resultado == "de_primeira" else 1, "brief": brief}
                d.update(extra)
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

    def ficha_json(self, tipo):
        p = self.run_op("ficha", "--tipo", tipo, "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)[0]

    def le(self, path, **kw):
        with io.open(path, encoding="utf-8", newline="", **kw) as f:
            return f.read()


class TestRegistrar(Base):
    def test_registrar_valido(self):
        p = self.reg("busca", "haiku", "de_primeira", licao="uma licao")
        d = json.loads(p.stdout)
        self.assertEqual(d["tipo"], "busca")
        self.assertEqual(len(d["id"]), 8)
        self.assertEqual(len(self.le(self.registro).strip().splitlines()), 1)

    def test_registrar_invalido(self):
        p = self.run_op("registrar", "--tipo", "busca", "--modelo", "haiku",
                        "--resultado", "de_primeira", "--rodadas", "2", "--brief", "1")
        self.assertEqual(p.returncode, 13)
        self.assertFalse(os.path.exists(self.registro))
        p = self.run_op("registrar", "--tipo", "busca", "--modelo", "haiku",
                        "--resultado", "corrigido", "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 13)
        p = self.run_op("registrar", "--tipo", "xxx", "--modelo", "haiku",
                        "--resultado", "falhou", "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 13)
        p = self.run_op("registrar", "--resultado", "falhou", "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 13)

    def test_redacao(self):
        segredo = "ghp_" + "AbCdEf0123456789XyZw"
        p = self.reg("busca", "haiku", "falhou", erros=["outro: vazou token " + segredo],
                     licao="usar " + segredo)
        self.assertNotIn(segredo, p.stdout)
        conteudo = self.le(self.registro)
        self.assertNotIn(segredo, conteudo)
        self.assertIn("REDIGIDO", conteudo)
        self.assertIn('"redigido"', conteudo)

    def test_status(self):
        p = self.run_op("status")
        self.assertEqual(p.returncode, 0)
        d = json.loads(p.stdout)
        self.assertEqual(d["canario"], "ok")
        self.assertEqual(d["n_registros"], 0)
        self.assertEqual(d["linhas_ignoradas"], 0)
        self.assertEqual(d["redacao"], "interno")

    def test_d6_ids_unicos(self):
        ids = set()
        for _ in range(4):
            p = self.reg("busca", "haiku", "de_primeira")
            ids.add(json.loads(p.stdout)["id"])
        self.assertEqual(len(ids), 4)

    def test_d5_erro_duplicado_no_mesmo_registro(self):
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["outro: a", "outro: a"])
        r = self.ficha_json("teste")
        self.assertEqual(r["avisos"], [])

    def test_sessao_gravada(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sess-xyz"
        p = self.reg("busca", "haiku", "de_primeira")
        self.assertEqual(json.loads(p.stdout)["sessao"], "sess-xyz")


def _trava_do_teste(caminho):
    """Pega a trava do registro num handle proprio (mesma chamada do SO que o motor usa)."""
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT)
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def _solta_trava_do_teste(fd):
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)


class TestTravaRegistro(Base):
    def _linhas(self):
        if not os.path.exists(self.registro):
            return []
        return [l for l in self.le(self.registro).splitlines() if l.strip()]

    def test_c1_registrar_espera_a_trava(self):
        import time
        os.makedirs(os.path.dirname(self.registro))
        fd = _trava_do_teste(self.registro + ".trava")
        proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable, SCRIPT, "registrar", "--tipo", "busca", "--modelo", "haiku",
                 "--resultado", "de_primeira", "--rodadas", "0", "--brief", "2"],
                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8")
            time.sleep(1.0)
            self.assertIsNone(proc.poll(), "registrar nao esperou a trava")
            self.assertEqual(self._linhas(), [])
            _solta_trava_do_teste(fd)
            fd = None
            out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0, err)
            self.assertEqual(len(self._linhas()), 1)
        finally:
            if fd is not None:
                _solta_trava_do_teste(fd)
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.communicate()

    def test_c1_sem_trava_apos_prazo_grava_com_aviso(self):
        os.makedirs(os.path.dirname(self.registro))
        trava = self.registro + ".trava"
        fd = _trava_do_teste(trava)
        chamou = []
        try:
            with mock.patch.object(operarios, "TRAVA_S", 0.3), \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                operarios._com_trava(trava, lambda: chamou.append(1))
        finally:
            _solta_trava_do_teste(fd)
        self.assertEqual(chamou, [1])
        self.assertIn("aviso: registro sem trava apos 10 s; gravando assim mesmo", err.getvalue())
        self.assertTrue(os.path.exists(trava))

    @unittest.skipUnless(os.environ.get("ORQ_TESTE_CARGA"), "carga: defina ORQ_TESTE_CARGA=1")
    def test_c1_carga_8x25(self):
        procs = []
        for _ in range(8):
            procs.append(subprocess.Popen(
                [sys.executable, "-c",
                 "import subprocess,sys\n"
                 "rc=0\n"
                 "for _ in range(25):\n"
                 "    rc|=subprocess.run([sys.executable,%r,'registrar','--tipo','busca','--modelo','haiku',"
                 "'--resultado','de_primeira','--rodadas','0','--brief','2'],"
                 "capture_output=True).returncode\n"
                 "sys.exit(rc)" % SCRIPT],
                env=self.env))
        for p in procs:
            self.assertEqual(p.wait(timeout=300), 0)
        self.assertEqual(len(self._linhas()), 200)


class TestLeituraRobusta(Base):
    def test_d1_linhas_ruins(self):
        os.makedirs(os.path.dirname(self.registro))
        with open(self.registro, "wb") as f:
            f.write(b'{"tipo":"busca","modelo":"haiku","resultado":"falhou","erros":[5],"brief":"x"}\n')
            f.write(b"\xe9 lixo\n")
            f.write(b"[1,2]\n")
            f.write(b'{"tipo":"zzz","modelo":"haiku","resultado":"falhou"}\n')
            f.write(b'{"tipo":"busca","modelo":"haiku","resultado":"de_primeira","licao":7}\n')
        p = self.run_op("ficha", "--tipo", "busca")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.run_op("status")
        d = json.loads(p.stdout)
        self.assertEqual(d["n_registros"], 2)
        self.assertEqual(d["linhas_ignoradas"], 3)
        p = self.run_op("atualizar")
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_d1_bom_utf8(self):
        os.makedirs(os.path.dirname(self.registro))
        with open(self.registro, "wb") as f:
            f.write(b'\xef\xbb\xbf{"tipo":"busca","modelo":"haiku","resultado":"falhou"}\n')
        d = json.loads(self.run_op("status").stdout)
        self.assertEqual(d["n_registros"], 1)


class TestRota(Base):
    def test_r1_sem_historico(self):
        p = self.run_op("ficha", "--json")
        self.assertEqual(p.returncode, 0)
        rotas = json.loads(p.stdout)
        self.assertEqual(len(rotas), len(operarios.TIPOS))
        por = {r["tipo"]: r for r in rotas}
        self.assertIn("coordenacao", por)
        for t, (m, b) in operarios.PADRAO.items():
            self.assertEqual(por[t]["modelo"], m)
            self.assertEqual(por[t]["brief"], b)
            if t in ("edicao-mecanica", "teste"):
                self.assertEqual(por[t]["experimento"]["modelo"], "haiku")
                self.assertEqual(por[t]["experimento"]["brief"], 3)
            else:
                self.assertIsNone(por[t]["experimento"], t)
        p = self.run_op("ficha")
        self.assertIn("rota padrao, sem historico", p.stdout)

    def test_r2_d7a_promocao_sem_contaminar(self):
        self.grava("edicao-mecanica", "sonnet", "falhou", n=4, brief=3)
        self.grava("edicao-mecanica", "haiku", "de_primeira", n=4, brief=2)
        r = self.ficha_json("edicao-mecanica")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 2))
        self.assertTrue(r["motivo"].startswith("promovido: haiku de primeira 4/4"), r["motivo"])
        self.assertNotIn("sonnet", r["motivo"])

    def test_r3_d7b_brief_do_balde(self):
        self.grava("teste", "haiku", "de_primeira", n=4, brief=2)
        r = self.ficha_json("teste")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 2))

    def test_r4_duro_sobe_brief_e_depois_modelo(self):
        self.grava("busca", "haiku", "falhou", n=3, brief=2)
        r = self.ficha_json("busca")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 3))
        self.grava("busca", "haiku", "falhou", n=3, brief=3)
        r = self.ficha_json("busca")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 2))
        self.assertIsNone(r["experimento"])

    def test_r5_precisa_ajuda(self):
        self.grava("busca", "haiku", "de_primeira", n=1, brief=2)
        self.grava("busca", "haiku", "corrigido", n=3, brief=2)
        r = self.ficha_json("busca")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 3))

    def test_r6_effort_high(self):
        self.grava("revisao", "sonnet", "corrigido", n=4, brief=2)
        r = self.ficha_json("revisao")
        self.assertEqual((r["modelo"], r["brief"], r["effort"]), ("sonnet", 3, None))
        self.grava("revisao", "sonnet", "corrigido", n=4, brief=3)
        r = self.ficha_json("revisao")
        self.assertEqual((r["modelo"], r["brief"], r["effort"]), ("sonnet", 3, "high"))

    def test_r7_ate_o_chefe(self):
        self.grava("revisao", "sonnet", "falhou", n=4, brief=2)
        r = self.ficha_json("revisao")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 3))
        self.grava("revisao", "sonnet", "falhou", n=3, brief=3)
        r = self.ficha_json("revisao")
        self.assertEqual((r["modelo"], r["brief"]), ("opus", 2))
        self.grava("revisao", "opus", "falhou", n=3, brief=2)
        self.grava("revisao", "opus", "falhou", n=3, brief=3)
        r = self.ficha_json("revisao")
        self.assertEqual(r["modelo"], "chefe")
        self.assertIsNone(r["brief"])
        self.assertIn("todos reprovados", r["motivo"])
        p = self.run_op("ficha", "--tipo", "revisao")
        self.assertIn("revisao -> chefe faz direto", p.stdout)

    def test_r8_reteste_antigo(self):
        self.grava("busca", "haiku", "falhou", n=3, brief=2, dias=40)
        self.grava("busca", "haiku", "falhou", n=3, brief=3, dias=40)
        r = self.ficha_json("busca")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 2))
        self.assertEqual(r["experimento"]["modelo"], "haiku")
        self.assertEqual(r["experimento"]["brief"], 3)
        self.assertIn("ultimo teste ha 40 dias: retestar", r["experimento"]["motivo"])

    def test_r9_brief_menor(self):
        self.grava("front", "sonnet", "de_primeira", n=6, brief=2)
        r = self.ficha_json("front")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 3))
        self.assertEqual(r["experimento"]["modelo"], "haiku")
        self.assertEqual(r["experimento"]["brief"], 3)
        self.assertIn("tarefa mais mecanica", r["experimento"]["motivo"])
        self.grava("revisao", "sonnet", "de_primeira", n=6, brief=2)
        r = self.ficha_json("revisao")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 2))
        self.assertIsNone(r["experimento"])

    def test_r9b_brief_menor_ligado(self):
        self.assertFalse(operarios.EXPERIMENTAR_BRIEF_MENOR)
        self.addCleanup(setattr, operarios, "EXPERIMENTAR_BRIEF_MENOR", False)
        operarios.EXPERIMENTAR_BRIEF_MENOR = True
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        regs = [operarios._norm_reg({"ts": ts, "tipo": "revisao", "modelo": "sonnet",
                                     "resultado": "de_primeira", "rodadas": 0, "brief": 2})
                for _ in range(6)]
        with mock.patch.dict(os.environ, {"ORQ_REGISTRO": self.registro, "ORQ_FICHA": self.ficha,
                                          "ORQ_PROJECTS": self.projects}):
            r = operarios.rota_tipo(regs, "revisao")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 2))
        self.assertEqual(r["experimento"]["modelo"], "sonnet")
        self.assertEqual(r["experimento"]["brief"], 1)
        self.assertIn("testar com menos detalhe", r["experimento"]["motivo"])

    def test_r10_avisos(self):
        self.grava("teste", "sonnet", "corrigido", n=3, erros=["Esqueceu o mock."])
        self.grava("teste", "sonnet", "corrigido", n=1, erros=["unico", "unico"])
        for i in range(4):
            self.grava("teste", "sonnet", "corrigido", n=2, erros=["erro%d" % i])
        r = self.ficha_json("teste")
        cuid = [a for a in r["avisos"] if a.startswith("cuidado")]
        self.assertTrue(any("esqueceu o mock (3x)" in a for a in cuid), cuid)
        self.assertFalse(any("unico" in a for a in r["avisos"]))
        self.assertEqual(len(cuid), 3)

    def test_r11_licoes(self):
        self.grava("teste", "sonnet", "falhou", n=1, licao="licao de falha")
        self.grava("teste", "sonnet", "de_primeira", n=1, licao="licao rara")
        self.grava("teste", "sonnet", "de_primeira", n=2, licao="Licao repetida")
        r = self.ficha_json("teste")
        self.assertNotIn("licao de falha", " ".join(r["licoes"]))
        self.assertTrue(r["licoes"][0].endswith("(2x)"), r["licoes"])
        self.assertEqual(len(r["licoes"]), 2)


class TestConferir(Base):
    def fazer_agente(self, base_dir, nome, meta, modelos, brief="faca X"):
        sub = os.path.join(base_dir, "subagents")
        os.makedirs(operarios._long(sub), exist_ok=True)
        mp = os.path.join(sub, "agent-%s.meta.json" % nome)
        with io.open(operarios._long(mp), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        if modelos is None:
            return
        with io.open(operarios._long(os.path.join(sub, "agent-%s.jsonl" % nome)), "w",
                     encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"role": "user", "content": brief}}) + "\n")
            for m in modelos:
                f.write(json.dumps({"type": "assistant", "message": {
                    "model": m, "usage": {"output_tokens": 10, "input_tokens": 5,
                                          "cache_read_input_tokens": 100,
                                          "cache_creation_input_tokens": 20}}}) + "\n")

    def test_ok(self):
        base = os.path.join(self.projects, "proj", "sess1")
        self.fazer_agente(base, "a1", {"description": "[haiku:busca] achar", "model": "haiku"},
                          ["claude-haiku-5-5", "claude-haiku-5-5"])
        p = self.run_op("conferir", "--desde", "1h", "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual(d[0]["status"], "ok")
        self.assertEqual(d[0]["tipo"], "busca")
        self.assertEqual(d[0]["tokens_saida"], 20)
        self.assertEqual(d[0]["contexto_max"], 125)

    def test_divergiu_e_resumo(self):
        base = os.path.join(self.projects, "proj", "sess1")
        self.fazer_agente(base, "a2", {"description": "x", "model": "sonnet"}, ["claude-opus-5-5"])
        self.fazer_agente(base, "a3", {"description": "y"}, ["claude-opus-5-5"])
        p = self.run_op("conferir", "--desde", "1h")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("DIVERGIU", p.stdout)
        self.assertIn("herdou", p.stdout)
        self.assertIn("2 agentes: 0 ok, 1 DIVERGIU, 1 herdou, 0 sem dado", p.stdout)

    def test_d4_sem_dado_e_id_completo(self):
        base = os.path.join(self.projects, "proj", "sess1")
        self.fazer_agente(base, "n1", {"description": "x", "model": "opus"}, None)
        p = self.run_op("conferir", "--desde", "1h", "--json")
        self.assertEqual(json.loads(p.stdout)[0]["status"], "SEM-DADO")
        self.assertEqual(p.returncode, 0)
        self.fazer_agente(base, "n2", {"description": "z", "model": "claude-opus-5-5"},
                          ["claude-opus-5-5"])
        self.fazer_agente(base, "n3", {"description": "w", "model": "claude-opus-5-5"},
                          ["claude-sonnet-5-5"])
        d = {a["agente"]: a["status"] for a in json.loads(
            self.run_op("conferir", "--desde", "1h", "--json").stdout)}
        self.assertEqual(d["agent-n2"] if "agent-n2" in d else d["n2"], "ok")
        self.assertEqual(d["agent-n3"] if "agent-n3" in d else d["n3"], "DIVERGIU")

    def test_nenhum(self):
        p = self.run_op("conferir", "--desde", "1h")
        self.assertEqual(p.returncode, 10)

    def test_n1_escopo_de_sessao(self):
        self.fazer_agente(os.path.join(self.projects, "proj", "sessA"), "a",
                          {"description": "da A", "model": "haiku"}, ["claude-haiku-5-5"])
        self.fazer_agente(os.path.join(self.projects, "proj", "sessB"), "b",
                          {"description": "da B", "model": "haiku"}, ["claude-haiku-5-5"])
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessA"
        d = json.loads(self.run_op("conferir", "--desde", "1h", "--json").stdout)
        self.assertEqual([a["descricao"] for a in d], ["da A"])
        d = json.loads(self.run_op("conferir", "--desde", "1h", "--json", "--todas").stdout)
        self.assertEqual(len(d), 2)
        d = json.loads(self.run_op("conferir", "--desde", "1h", "--json", "--sessao", "sessB").stdout)
        self.assertEqual([a["descricao"] for a in d], ["da B"])
        del self.env["CLAUDE_CODE_SESSION_ID"]
        d = json.loads(self.run_op("conferir", "--desde", "1h", "--json").stdout)
        self.assertEqual(len(d), 2)

    def test_caminho_longo(self):
        base = os.path.join(self.projects, "p" * 120, "s" * 120)
        self.assertGreater(len(os.path.join(base, "subagents", "agent-zz.meta.json")), 260)
        self.fazer_agente(base, "zz", {"description": "longo", "model": "haiku"},
                          ["claude-haiku-5-5"])
        p = self.run_op("conferir", "--desde", "1h", "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["reais"], {"claude-haiku-5-5": 1})

    def test_n2_registrar_agente(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessA"
        base = os.path.join(self.projects, "proj", "sessA")
        self.fazer_agente(base, "q1", {"description": "[haiku:busca] achar os arquivos", "model": "haiku"},
                          ["claude-haiku-5-5"] * 3, brief="BRIEF DO AGENTE")
        self.fazer_agente(base, "q2", {"description": "outra coisa"}, ["claude-opus-5-5"])
        p = self.run_op("registrar", "--agente", "[HAIKU:busca] achar", "--resultado", "de_primeira",
                        "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual((d["tipo"], d["modelo"], d["tokens_saida"], d["sessao"]),
                         ("busca", "haiku", 30, "sessA"))
        ex = os.path.join(os.path.dirname(self.registro), "exemplos", "busca--haiku.md")
        self.assertIn("BRIEF DO AGENTE", self.le(ex))
        r = self.ficha_json("busca")
        self.assertEqual(r["exemplo"], ex)
        # sem casar
        p = self.run_op("registrar", "--agente", "nao existe", "--resultado", "falhou",
                        "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 13)
        # modelo informado diferente do real: grava o real
        p = self.run_op("registrar", "--agente", "outra", "--tipo", "debug", "--modelo", "sonnet",
                        "--resultado", "falhou", "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("AVISO: pedido sonnet, rodou opus", p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual((d["modelo"], d["pedido"]), ("opus", "sonnet"))
        # sem tag e sem --tipo
        p = self.run_op("registrar", "--agente", "outra", "--resultado", "falhou",
                        "--rodadas", "0", "--brief", "1")
        self.assertEqual(p.returncode, 13)

    def test_c2_descricao_igual_vence_prefixo(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessA"
        base = os.path.join(self.projects, "proj", "sessA")
        curto = "[sonnet:front] cartao na lista"
        self.fazer_agente(base, "c1", {"description": curto, "model": "sonnet"},
                          ["claude-sonnet-5-5"] * 2)
        self.fazer_agente(base, "c2", {"description": curto + " de clientes", "model": "sonnet"},
                          ["claude-sonnet-5-5"] * 5)
        args = ["--resultado", "de_primeira", "--rodadas", "0", "--brief", "2"]
        # igual unico + prefixo de outro: devolve o igual (2 respostas = 20 tokens de saida)
        p = self.run_op("registrar", "--agente", curto, *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["tokens_saida"], 20)
        # so prefixos, nenhum igual, 1 candidato: devolve ele (5 respostas)
        p = self.run_op("registrar", "--agente", curto + " de", *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["tokens_saida"], 50)
        # so prefixos, nenhum igual, 2 candidatos: erro
        p = self.run_op("registrar", "--agente", "[sonnet:front] cartao", *args)
        self.assertEqual(p.returncode, 13)
        self.assertIn("mais de um agente", p.stderr)
        # 2 iguais: erro
        self.fazer_agente(base, "c3", {"description": curto, "model": "sonnet"},
                          ["claude-sonnet-5-5"] * 3)
        p = self.run_op("registrar", "--agente", curto, *args)
        self.assertEqual(p.returncode, 13)
        self.assertIn("mais de um agente", p.stderr)

    def test_c3_model_inherit_herdou(self):
        base = os.path.join(self.projects, "proj", "sess1")
        self.fazer_agente(base, "i1", {"description": "[sonnet:front] fork", "model": "inherit"},
                          ["claude-opus-5-5"])
        self.fazer_agente(base, "i2", {"description": "[sonnet:front] fork2", "model": "Inherit"},
                          ["claude-opus-5-5"])
        p = self.run_op("conferir", "--desde", "1h", "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        for a in json.loads(p.stdout):
            self.assertEqual(a["status"], "herdou", a)

    def test_d6_tokens_por_resposta(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessU"
        sub = os.path.join(self.projects, "proj", "sessU", "subagents")
        os.makedirs(operarios._long(sub), exist_ok=True)
        with io.open(operarios._long(os.path.join(sub, "agent-u1.meta.json")), "w", encoding="utf-8") as f:
            json.dump({"description": "[haiku:busca] dedup", "model": "haiku"}, f)
        def usage(mid, out, inp, cache):
            return {"type": "assistant", "message": {"id": mid, "model": "claude-haiku-5-5", "usage": {
                "output_tokens": out, "input_tokens": inp, "cache_read_input_tokens": cache,
                "cache_creation_input_tokens": 0}}}
        linhas = [{"type": "user", "message": {"role": "user", "content": "faca X"}},
                  usage("msg_A", 100, 5, 1000), usage("msg_A", 100, 5, 1000),
                  usage("msg_B", 50, 5, 2000)]
        with io.open(operarios._long(os.path.join(sub, "agent-u1.jsonl")), "w", encoding="utf-8") as f:
            for l in linhas:
                f.write(json.dumps(l) + "\n")
        d = json.loads(self.run_op("conferir", "--desde", "1h", "--json").stdout)[0]
        self.assertEqual((d["tokens_saida"], d["respostas"], d["contexto_max"], d["reais"]),
                         (150, 2, 2005, {"claude-haiku-5-5": 2}))
        p = self.run_op("conferir", "--desde", "1h")
        self.assertIn("claude-haiku-5-5 x2", p.stdout)
        p = self.run_op("registrar", "--agente", "[haiku:busca] dedup", "--resultado", "de_primeira",
                        "--rodadas", "0", "--brief", "2")
        self.assertEqual(p.returncode, 0, p.stderr)
        rec = json.loads(p.stdout)
        self.assertEqual((rec["tokens_saida"], rec["respostas"], rec["tokens_v"]), (150, 2, 2))

    def test_t6_modo_god_arvore(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessM"
        base = os.path.join(self.projects, "proj", "sessM")
        self.fazer_agente(base, "b0", {"description": "[haiku:busca] avulso", "model": "haiku",
                                       "spawnDepth": 1}, ["claude-haiku-5-5"])
        self.fazer_agente(base, "pai1", {"description": "[opus:coordenacao] mestre X", "model": "opus",
                                         "spawnDepth": 1}, ["claude-opus-5-5"])
        self.fazer_agente(base, "filho1", {"description": "[sonnet:edicao-logica] filho Y",
                                           "model": "sonnet", "spawnDepth": 2,
                                           "parentAgentId": "pai1"}, ["claude-sonnet-5-5"])
        p = self.run_op("conferir", "--desde", "1h")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        linhas = p.stdout.splitlines()
        i = next(k for k, l in enumerate(linhas) if "[opus:coordenacao] mestre X" in l)
        self.assertIsNotNone(re.search(r"\s2\s+" + chr(0x2514) + r" \[sonnet:edicao-logica\] filho Y",
                                       linhas[i + 1]), linhas[i + 1])
        self.assertIn(", 1 netos", linhas[-1])
        d = json.loads(self.run_op("conferir", "--desde", "1h", "--json").stdout)
        self.assertEqual([a["descricao"] for a in d],
                         ["[haiku:busca] avulso", "[opus:coordenacao] mestre X",
                          "[sonnet:edicao-logica] filho Y"])
        self.assertEqual(d[2]["profundidade"], 2)
        p = self.run_op("registrar", "--agente", "[sonnet:edicao-logica] filho", "--frente", "motor",
                        "--resultado", "de_primeira", "--rodadas", "0", "--brief", "3")
        self.assertEqual(p.returncode, 0, p.stderr)
        rec = json.loads(p.stdout)
        self.assertEqual(rec["profundidade"], 2)
        self.assertEqual(rec["mestre"], "[opus:coordenacao] mestre X")
        self.assertEqual(rec["frente"], "motor")
        p = self.run_op("registrar", "--agente", "[opus:coordenacao] mestre", "--resultado",
                        "de_primeira", "--rodadas", "0", "--brief", "2")
        self.assertEqual(p.returncode, 0, p.stderr)
        rec = json.loads(p.stdout)
        self.assertEqual(rec["profundidade"], 1)
        self.assertNotIn("mestre", rec)
        p = self.run_op("registrar", "--tipo", "busca", "--modelo", "haiku", "--resultado", "anulado",
                        "--rodadas", "0", "--brief", "2", "--frente", "motor")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.run_op("registrar", "--tipo", "busca", "--modelo", "haiku", "--resultado", "de_primeira",
                        "--rodadas", "0", "--brief", "2", "--frente", "   ")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("frente", json.loads(p.stdout))
        p = self.run_op("resumo", "--por-frente")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("  motor: 1 tarefas, 1 de primeira, 0 corrigidas, 0 falharam, saida ", p.stdout)
        # mestre (sem --frente) + o de frente vazia
        self.assertIn("  (sem frente): 2 tarefas", p.stdout)

    def test_t6b_erros_de_obra(self):
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessD"
        base = os.path.join(self.projects, "proj", "sessD")
        self.fazer_agente(base, "p1", {"description": "[opus:coordenacao] mestre Z", "model": "opus",
                                       "spawnDepth": 1}, ["claude-opus-5-5"])
        self.fazer_agente(base, "n1", {"description": "[sonnet:busca] neto sem modelo",
                                       "spawnDepth": 2, "parentAgentId": "p1"}, ["claude-opus-5-5"])
        self.fazer_agente(base, "b1", {"description": "[haiku:busca] bisneto", "model": "haiku",
                                       "spawnDepth": 3, "parentAgentId": "n1"}, ["claude-haiku-5-5"])
        self.fazer_agente(base, "b2", {"description": "[haiku:busca] bisneto sem modelo",
                                       "spawnDepth": 3, "parentAgentId": "n1"}, ["claude-haiku-5-5"])
        p = self.run_op("conferir", "--desde", "1h")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("SEM-MODELO", p.stdout)
        self.assertIn("ANDAR-3", p.stdout)
        self.assertIn(", 2 bisnetos (PROIBIDO)", p.stdout.splitlines()[-1])
        d = {a["descricao"]: a["status"] for a in json.loads(
            self.run_op("conferir", "--desde", "1h", "--json").stdout)}
        self.assertEqual(d["[opus:coordenacao] mestre Z"], "ok")
        self.assertEqual(d["[sonnet:busca] neto sem modelo"], "SEM-MODELO")
        self.assertEqual(d["[haiku:busca] bisneto"], "ANDAR-3")
        self.assertEqual(d["[haiku:busca] bisneto sem modelo"], "ANDAR-3")
        self.env["CLAUDE_CODE_SESSION_ID"] = "sessE"
        base = os.path.join(self.projects, "proj", "sessE")
        self.fazer_agente(base, "s1", {"description": "solto"}, ["claude-opus-5-5"])
        p = self.run_op("conferir", "--desde", "1h", "--json", "--sessao", "sessE")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(json.loads(p.stdout)[0]["status"], "herdou")
        base = os.path.join(self.projects, "proj", "sessF")
        self.fazer_agente(base, "pF", {"description": "pai F", "model": "opus", "spawnDepth": 1},
                          ["claude-opus-5-5"])
        self.fazer_agente(base, "nF", {"description": "neto F", "spawnDepth": 2, "parentAgentId": "pF"},
                          ["claude-opus-5-5"])
        p = self.run_op("conferir", "--desde", "1h", "--sessao", "sessF")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)


class TestResumo(Base):
    def test_n3_resumo(self):
        p = self.run_op("resumo")
        self.assertEqual(p.returncode, 10)
        self.assertIn("nenhuma tarefa registrada", p.stdout)
        self.grava("busca", "haiku", "de_primeira", n=2, sessao="S1")
        self.grava("busca", "sonnet", "falhou", n=1, sessao="S1")
        self.grava("busca", "haiku", "corrigido", n=1, sessao="S2")
        p = self.run_op("resumo", "--todas")
        self.assertEqual(p.returncode, 0)
        self.assertIn("operarios: 4 tarefas, 2 de primeira, 1 corrigidas, 0 escaladas, 1 falharam", p.stdout)
        self.assertIn("haiku 2/3 de primeira; sonnet 0/1 de primeira", p.stdout)
        self.env["CLAUDE_CODE_SESSION_ID"] = "S1"
        p = self.run_op("resumo")
        self.assertIn("3 tarefas", p.stdout)


class TestAtualizar(Base):
    def test_sem_orq_ficha_avisa_e_nao_grava(self):
        self.reg("busca", "haiku", "de_primeira", licao="grep primeiro")
        self.env.pop("ORQ_FICHA", None)
        p = self.run_op("atualizar")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("aviso: ORQ_FICHA nao definida; ficha nao gravada", p.stderr)
        self.assertFalse(os.path.exists(self.ficha))
        self.assertEqual(os.listdir(self.tmp).count("ficha.md"), 0)

    def test_cria_e_preserva(self):
        self.reg("busca", "haiku", "de_primeira", licao="grep primeiro")
        p = self.run_op("atualizar")
        self.assertEqual(p.returncode, 0, p.stderr)
        t = self.le(self.ficha)
        self.assertTrue(t.startswith("---\nname: fichas-operarios"))
        self.assertIn(operarios.MARC_INI, t)
        self.assertIn(operarios.MARC_FIM, t)
        self.assertIn("| tipo | rota atual |", t)
        self.assertIn("grep primeiro", t)
        self.assertIn("## Exemplos de brief", t)
        self.assertFalse(t.startswith(u"﻿"))
        self.assertNotIn("\r", t)
        t2 = t.replace("# Fichas dos operarios",
                       "NOTA MANUAL ACENTO ação\n# Fichas dos operarios")
        t2 += "\nRODAPE MANUAL\n"
        with io.open(self.ficha, "w", encoding="utf-8", newline="") as f:
            f.write(t2)
        self.reg("busca", "haiku", "de_primeira", licao="outra licao")
        p = self.run_op("atualizar")
        self.assertEqual(p.returncode, 0, p.stderr)
        t3 = self.le(self.ficha)
        self.assertIn("NOTA MANUAL ACENTO ação", t3)
        self.assertTrue(t3.endswith("RODAPE MANUAL\n"))
        self.assertIn("outra licao", t3)
        i = t2.find(operarios.MARC_INI)
        j = t2.find(operarios.MARC_FIM) + len(operarios.MARC_FIM)
        i3 = t3.find(operarios.MARC_INI)
        j3 = t3.find(operarios.MARC_FIM) + len(operarios.MARC_FIM)
        self.assertEqual(t2[:i], t3[:i3])
        self.assertEqual(t2[j:], t3[j3:])

    def test_d2_marcadores_inconsistentes(self):
        original = "NOTA A\n<!-- auto:inicio -->\nvelho\nNOTA B DO USUARIO\n"
        with io.open(self.ficha, "w", encoding="utf-8", newline="") as f:
            f.write(original)
        p = self.run_op("atualizar")
        self.assertEqual(p.returncode, 13)
        self.assertEqual(self.le(self.ficha), original)
        # ordem trocada
        trocado = "a\n<!-- auto:fim -->\nb\n<!-- auto:inicio -->\nc\n"
        with io.open(self.ficha, "w", encoding="utf-8", newline="") as f:
            f.write(trocado)
        self.assertEqual(self.run_op("atualizar").returncode, 13)
        self.assertEqual(self.le(self.ficha), trocado)
        # duplicado
        dup = ("<!-- auto:inicio -->\n<!-- auto:fim -->\n<!-- auto:inicio -->\n"
               "<!-- auto:fim -->\n")
        with io.open(self.ficha, "w", encoding="utf-8", newline="") as f:
            f.write(dup)
        self.assertEqual(self.run_op("atualizar").returncode, 13)
        self.assertEqual(self.le(self.ficha), dup)

    def test_sem_marcador_anexa_e_crlf(self):
        with io.open(self.ficha, "w", encoding="utf-8", newline="") as f:
            f.write("linha1\r\nlinha2\r\n")
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        t = self.le(self.ficha)
        self.assertTrue(t.startswith("linha1\r\nlinha2\r\n"))
        self.assertIn(operarios.MARC_FIM, t)
        self.assertEqual(t.count("\n"), t.count("\r\n"))
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        t2 = self.le(self.ficha)
        self.assertEqual(t2.count("\n"), t2.count("\r\n"))
        self.assertEqual(t2.count(operarios.MARC_INI), 1)

    def test_d3_marcador_na_licao(self):
        self.reg("busca", "haiku", "de_primeira",
                 licao="x <!-- auto:fim --> LIXO | col\nnova linha")
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        t = self.le(self.ficha)
        self.assertEqual(t.count(operarios.MARC_FIM), 1)
        self.assertEqual(t.count(operarios.MARC_INI), 1)
        with io.open(self.ficha, "a", encoding="utf-8", newline="") as f:
            f.write("nota\n")
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        t = self.le(self.ficha)
        self.assertEqual(t.count("LIXO"), 1)
        self.assertEqual(t.count(operarios.MARC_FIM), 1)


class TestAnulado(Base):
    def test_t1_anulado_nao_mexe_na_rota(self):
        for r in ("0", "0", "2"):
            p = self.run_op("registrar", "--tipo", "busca", "--modelo", "haiku",
                            "--resultado", "anulado", "--rodadas", r, "--brief", "2",
                            "--erro", "leitura: inventou caminho")
            self.assertEqual(p.returncode, 0, p.stderr)
        self.reg("busca", "haiku", "de_primeira", brief=2)
        r = self.ficha_json("busca")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 2))
        self.assertFalse(any(a.startswith("geral:") or "inventou caminho" in a for a in r["avisos"]),
                         r["avisos"])
        p = self.run_op("resumo")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("3 anuladas", p.stdout)
        self.assertIn("operarios: 1 tarefas", p.stdout)

    def test_t1_falhou_no_lugar_sobe_brief(self):
        self.grava("busca", "haiku", "falhou", n=3, brief=2)
        r = self.ficha_json("busca")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 3))


class TestClasseErro(Base):
    def avisos(self, tipo):
        return self.ficha_json(tipo)["avisos"]

    def test_t2_classe_gravada(self):
        p = self.run_op("registrar", "--tipo", "teste", "--modelo", "sonnet", "--resultado", "corrigido",
                        "--rodadas", "1", "--brief", "2", "--erro", "estado: fechou so a entrada")
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual(d["classes"], ["estado"])
        self.assertEqual(d["erros"], ["fechou so a entrada"])
        p = self.run_op("registrar", "--tipo", "teste", "--modelo", "sonnet", "--resultado", "corrigido",
                        "--rodadas", "1", "--brief", "2", "--erro", "texto sem classe")
        self.assertEqual(p.returncode, 13)
        self.assertIn("--erro sem classe", p.stderr)
        self.assertEqual(len(self.le(self.registro).strip().splitlines()), 1)

    def test_t2_dois_da_mesma_classe_geram_aviso(self):
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["estado: fechou so a entrada"])
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["estado: esqueceu o cache do lote"])
        avisos = self.avisos("teste")
        self.assertTrue(any(a.startswith("cuidado: 2 de 2 entregas com erro foram de estado")
                            and "(ultimo: esqueceu o cache do lote)" in a for a in avisos), avisos)
        self.assertTrue(any(a.endswith(" -> no brief: a ordem dos eventos e o que acontece ao repetir, "
                                       "cancelar, recarregar") for a in avisos), avisos)

    def test_t2_um_so_nao_gera_aviso_de_classe(self):
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["estado: fechou so a entrada"])
        self.assertFalse(any("entregas com erro foram de" in a for a in self.avisos("teste")))

    def test_t2_mesmo_texto_continua_aviso_de_texto(self):
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["estado: fechou so a entrada"])
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["estado: fechou so a entrada"])
        avisos = self.avisos("teste")
        self.assertTrue(avisos[0].startswith("cuidado: 2 de 2 entregas com erro foram de estado"), avisos)
        self.assertIn("cuidado: fechou so a entrada (2x)", avisos)

    def test_t2_formato_antigo_sem_classe(self):
        self.grava("teste", "sonnet", "corrigido", n=1, erros=["estado: x"])
        self.grava("teste", "sonnet", "corrigido", n=1, erros=["estado: y"])
        self.assertFalse(any("entregas com erro foram de" in a for a in self.avisos("teste")))

    def test_t2g_teto_de_avisos_de_classe(self):
        for _ in range(2):
            self.reg("teste", "sonnet", "corrigido", rodadas=1, brief=2,
                     erros=["estado: a", "borda: b", "contrato: c", "escopo: d"])
        avisos = self.avisos("teste")
        self.assertEqual(len(avisos), 3, avisos)
        self.assertTrue(all("entregas com erro foram de" in a for a in avisos), avisos)

    def test_t2_help_lista_classes(self):
        p = self.run_op("registrar", "--help")
        self.assertEqual(p.returncode, 0, p.stderr)
        for c in ("escopo", "contrato", "borda", "estado", "desempenho", "teste",
                  "alegacao", "leitura", "visual", "seguranca"):
            self.assertIn("  " + c + ":", p.stdout)


class TestBriefSegueProva(Base):
    def test_t3_leitura_brief_com_prova(self):
        self.grava("leitura", "haiku", "de_primeira", n=9, brief=2)
        r = self.ficha_json("leitura")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 2))
        self.assertIsNone(r["experimento"])

    def test_t3_brief_3_com_prova_quando_2_nao_tem(self):
        self.grava("pesquisa-web", "haiku", "de_primeira", n=4, brief=3)
        r = self.ficha_json("pesquisa-web")
        self.assertEqual((r["modelo"], r["brief"]), ("haiku", 3))
        self.assertIn("sem prova com brief 2; provado com brief 3 (4/4)", r["motivo"])

    def test_t3c_a3_pega_o_menor_nivel(self):
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        regs = [operarios._norm_reg({"ts": ts, "tipo": "busca", "modelo": "haiku",
                                     "resultado": "de_primeira", "rodadas": 0, "brief": 2})
                for _ in range(4)]
        regs += [operarios._norm_reg({"ts": ts, "tipo": "busca", "modelo": "haiku",
                                      "resultado": "de_primeira", "rodadas": 0, "brief": 3})
                 for _ in range(4)]
        with mock.patch.dict(os.environ, {"ORQ_REGISTRO": self.registro, "ORQ_FICHA": self.ficha,
                                          "ORQ_PROJECTS": self.projects}):
            usar, L, eff, mot = operarios._avaliar(regs, "busca", "haiku", 1)
        self.assertTrue(usar)
        self.assertEqual(L, 2)
        self.assertIn("provado com brief 2 (4/4)", " ".join(mot))


class TestExperimentoForte(Base):
    def setup_front_forte(self):
        self.grava("front", "sonnet", "de_primeira", n=5, brief=2)
        self.grava("front", "sonnet", "corrigido", n=1, brief=2)

    def test_t4_front_forte_sugere_haiku(self):
        self.setup_front_forte()
        r = self.ficha_json("front")
        self.assertEqual((r["modelo"], r["brief"]), ("sonnet", 3))
        self.assertEqual(r["experimento"]["modelo"], "haiku")
        self.assertEqual(r["experimento"]["brief"], 3)
        self.assertIn("sonnet acerta 5/6 de primeira", r["experimento"]["motivo"])
        self.assertIn("tarefa mais mecanica", r["experimento"]["motivo"])

    def test_t4_prova_do_par_inteiro(self):
        self.grava("front", "sonnet", "de_primeira", n=3, brief=2)
        self.grava("front", "sonnet", "de_primeira", n=3, brief=3)
        r = self.ficha_json("front")
        self.assertEqual(r["experimento"]["modelo"], "haiku")
        self.assertEqual(r["experimento"]["brief"], 3)
        self.assertIn("sonnet acerta 6/6 de primeira", r["experimento"]["motivo"])

    def test_c15_motivo_diz_de_onde_vem_a_conta(self):
        # prova no par inteiro: 3 + 3 de primeira (nenhum nivel sozinho atinge o minimo)
        self.grava("front", "sonnet", "de_primeira", n=3, brief=2)
        self.grava("front", "sonnet", "de_primeira", n=3, brief=3)
        m = self.ficha_json("front")["experimento"]["motivo"]
        self.assertIn("sonnet acerta 6/6 de primeira (todos os briefs)", m)

    def test_c15_motivo_com_nivel_do_brief(self):
        self.grava("front", "sonnet", "de_primeira", n=12, brief=2)
        self.grava("front", "sonnet", "corrigido", n=4, brief=2)
        self.grava("front", "sonnet", "corrigido", n=1, brief=3)
        m = self.ficha_json("front")["experimento"]["motivo"]
        self.assertIn("sonnet acerta 12/16 de primeira (brief 2)", m)

    def test_t4_registro_solto_de_outro_nivel_nao_dilui(self):
        # 12/16 no brief 2 e forte; 1 corrigido solto no brief 3 levaria o par inteiro a 12/17 (0,71) e apagava o experimento
        self.grava("front", "sonnet", "de_primeira", n=12, brief=2)
        self.grava("front", "sonnet", "corrigido", n=4, brief=2)
        self.grava("front", "sonnet", "corrigido", n=1, brief=3)
        r = self.ficha_json("front")
        self.assertEqual(r["experimento"]["modelo"], "haiku")
        self.assertIn("sonnet acerta 12/16 de primeira", r["experimento"]["motivo"])

    def test_t4_front_fraco_nao_sugere(self):
        self.grava("front", "sonnet", "de_primeira", n=4, brief=2)
        self.grava("front", "sonnet", "corrigido", n=2, brief=2)
        self.assertIsNone(self.ficha_json("front")["experimento"])

    def test_t4_revisao_nao_sugere_haiku(self):
        self.grava("revisao", "sonnet", "de_primeira", n=6, brief=2)
        self.grava("revisao", "haiku", "de_primeira", n=1, brief=2)
        r = self.ficha_json("revisao")
        self.assertIsNone(r["experimento"])

    def test_t4e_sem_barato_outros_tipos(self):
        for tipo, abaixo in [("debug", "haiku"), ("dados-sql", "haiku"), ("coordenacao", "sonnet")]:
            with self.subTest(tipo=tipo):
                self.grava(tipo, abaixo, "de_primeira", n=1, brief=2)
                self.grava(tipo, abaixo, "falhou", n=3, brief=3, dias=40)
                r = self.ficha_json(tipo)
                self.assertTrue(r["experimento"] is None or r["experimento"]["modelo"] != abaixo,
                                r["experimento"])

    def test_t4_andamento_do_experimento(self):
        self.setup_front_forte()
        p = self.run_op("registrar", "--tipo", "front", "--modelo", "haiku", "--resultado", "de_primeira",
                        "--rodadas", "0", "--brief", "2", "--experimento")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.run_op("registrar", "--tipo", "front", "--modelo", "haiku", "--resultado", "de_primeira",
                        "--rodadas", "0", "--brief", "3", "--experimento")
        self.assertEqual(p.returncode, 0, p.stderr)
        p = self.run_op("ficha", "--tipo", "front")
        self.assertIn("experimento: haiku brief 3 (", p.stdout)
        self.assertIn("feitos 1 de 4", p.stdout)


class TestCusto(Base):
    def test_t5_saida_por_modelo(self):
        self.grava("busca", "haiku", "de_primeira", n=1, brief=1, tokens_saida=200000, tokens_v=2)
        self.grava("busca", "haiku", "corrigido", n=1, brief=1, tokens_saida=110000, tokens_v=2)
        self.grava("busca", "sonnet", "de_primeira", n=1, brief=1, tokens_saida=1200000, tokens_v=2)
        self.grava("busca", "opus", "de_primeira", n=1, brief=1)
        self.grava("busca", "haiku", "anulado", n=1, brief=1, tokens_saida=5000000, tokens_v=2)
        p = self.run_op("resumo", "--todas")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        esperado = "| saida: haiku 0,31M" + " " + chr(0xB7) + " " + "sonnet 1,2M | haiku fez 2 de 4"
        self.assertIn(esperado, p.stdout)
        self.assertIn("1 anuladas", p.stdout)
        self.assertIn("operarios: 4 tarefas", p.stdout)

    def test_t5_mediana_na_ficha(self):
        for t in (10000, 20000, 90000):
            self.grava("busca", "haiku", "de_primeira", n=1, brief=1, tokens_saida=t, tokens_v=2)
        self.grava("busca", "haiku", "de_primeira", n=1, brief=1, tokens_saida=500000)
        p = self.run_op("ficha", "--tipo", "busca")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("~20k", p.stdout)

    def test_t5b_so_tokens_v2_no_resumo(self):
        self.grava("busca", "haiku", "de_primeira", n=1, brief=1, tokens_saida=200000, tokens_v=2)
        self.grava("busca", "haiku", "de_primeira", n=1, brief=1, tokens_saida=900000)
        self.grava("busca", "haiku", "de_primeira", n=1, brief=1, tokens_saida=True, tokens_v=2)
        p = self.run_op("resumo", "--todas")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("| saida: haiku 0,20M | haiku fez 3 de 3", p.stdout)

    def test_t5e_token_bool_nao_conta(self):
        self.grava("busca", "haiku", "de_primeira", n=1, brief=2, tokens_saida=True, tokens_v=2)
        p = self.run_op("ficha", "--tipo", "busca")
        self.assertEqual(p.returncode, 0, p.stderr)
        stats = [l for l in p.stdout.splitlines() if l.strip().startswith("stats:")]
        self.assertTrue(stats, p.stdout)
        self.assertNotIn("~", stats[0])

    def test_t5d_por_frente_sem_token_v2_mostra_traco(self):
        # registro antigo (sem tokens_v) nao vira "custo zero" na linha da frente
        self.grava("busca", "haiku", "de_primeira", n=1, brief=2, tokens_saida=900000, frente="velha")
        self.grava("busca", "haiku", "de_primeira", n=1, brief=2, tokens_saida=300000, tokens_v=2,
                   frente="nova")
        p = self.run_op("resumo", "--todas", "--por-frente")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("  velha: 1 tarefas, 1 de primeira, 0 corrigidas, 0 falharam, saida -", p.stdout)
        self.assertIn("  nova: 1 tarefas, 1 de primeira, 0 corrigidas, 0 falharam, saida 0,30M", p.stdout)

    def test_t5c_fmt_mi(self):
        self.assertEqual(operarios._fmt_mi(310000), "0,31M")
        self.assertEqual(operarios._fmt_mi(1200000), "1,2M")
        self.assertEqual(operarios._fmt_mi(999999), "1,0M")
        self.assertEqual(operarios._fmt_mi(0), "0,00M")


class TestRetomar(Base):
    def agente(self, sessao, nome, desc, modelo="claude-sonnet-5-5"):
        sub = os.path.join(self.projects, "proj", sessao, "subagents")
        os.makedirs(operarios._long(sub), exist_ok=True)
        with io.open(operarios._long(os.path.join(sub, "agent-%s.meta.json" % nome)), "w",
                     encoding="utf-8") as f:
            json.dump({"description": desc, "model": "sonnet"}, f)
        with io.open(operarios._long(os.path.join(sub, "agent-%s.jsonl" % nome)), "w",
                     encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "m1", "model": modelo, "usage": {"output_tokens": 10}}}) + "\n")

    def reg_ag(self, sessao, nome, resultado):
        self.grava("edicao-logica", "sonnet", resultado, sessao=sessao, agente="agent-%s" % nome)

    def run_in(self, entrada, *args):
        return subprocess.run([sys.executable, SCRIPT] + list(args), env=self.env, input=entrada,
                              capture_output=True, text=True, encoding="utf-8")

    def cenario3(self):
        self.agente("S", "a1", "[sonnet:edicao-logica] um")
        self.agente("S", "a2", "[sonnet:edicao-logica] dois")
        self.agente("S", "a3", "[sonnet:edicao-logica] tres")
        self.reg_ag("S", "a1", "de_primeira")
        self.reg_ag("S", "a2", "corrigido")

    def test_1_parcial(self):
        self.cenario3()
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[0],
                         "orquestrador: esta sessao ja despachou 3 operarios (2 registrados, 1 sem registro).")
        self.assertIn("tres", p.stdout)
        self.assertNotIn("] um", p.stdout)
        self.assertNotIn("] dois", p.stdout)
        self.assertIn("registrados: 1 de_primeira, 1 corrigido", p.stdout)
        self.assertIn("modelo real: claude-sonnet-5-5 | 1 respostas", p.stdout)

    def test_2_todos_registrados(self):
        self.cenario3()
        self.reg_ag("S", "a3", "falhou")
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("sem registro (", p.stdout)
        self.assertIn("registrados:", p.stdout)

    def test_3_nenhum_registrado(self):
        self.agente("S", "a1", "[sonnet:edicao-logica] um")
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("1 operario (0 registrados, 1 sem registro)", p.stdout)
        self.assertNotIn("registrados:", p.stdout)

    def test_4_sem_agente(self):
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 10)
        self.assertIn("nenhum operario", p.stdout)

    def test_5_sem_sessao(self):
        p = self.run_in("", "retomar")
        self.assertEqual(p.returncode, 2)
        self.assertIn("sem sessao", p.stderr)

    def test_6_hook_stdin(self):
        self.cenario3()
        p = self.run_in('{"session_id": "S", "source": "compact"}', "retomar", "--hook")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[0],
                         "orquestrador: esta sessao ja despachou 3 operarios (2 registrados, 1 sem registro).")
        self.assertIn("registrados: 1 de_primeira, 1 corrigido", p.stdout)

    def test_7_hook_stdin_vazio(self):
        p = self.run_in("", "retomar", "--hook")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertEqual(p.stderr, "")

    def test_8_hook_stdin_lixo(self):
        p = self.run_in("isto nao e json", "retomar", "--hook")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertEqual(p.stderr, "")

    def test_9_hook_sessao_sem_agente(self):
        p = self.run_in('{"session_id": "VAZIA"}', "retomar", "--hook")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")

    def test_10_registro_de_outra_sessao(self):
        self.agente("S", "a1", "[sonnet:edicao-logica] um")
        self.reg_ag("OUTRA", "a1", "de_primeira")
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("(0 registrados, 1 sem registro)", p.stdout)
        self.assertNotIn("registrados:", p.stdout)

    def test_11_limite_de_15(self):
        for i in range(17):
            self.agente("S", "b%02d" % i, "[sonnet:edicao-logica] t%02d" % i)
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(sum(1 for l in p.stdout.splitlines() if l.startswith("  - ")), 15)
        self.assertIn("  ... e mais 2", p.stdout.splitlines())

    def test_12_json(self):
        self.cenario3()
        p = self.run_op("retomar", "--sessao", "S", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual(d["operarios"], 3)
        self.assertEqual(d["registrados"], 2)
        self.assertEqual(len(d["sem_registro"]), 1)
        self.assertEqual(d["resultados"], {"de_primeira": 1, "corrigido": 1})

    def test_13_desde_invalido(self):
        self.cenario3()
        p = self.run_op("retomar", "--sessao", "S", "--desde", "abc")
        self.assertEqual(p.returncode, 13)
        p = self.run_in("", "retomar", "--sessao", "S", "--desde", "abc", "--hook")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        self.assertEqual(p.stderr, "")

    def papel(self, sessao, nome, desc, papel):
        """Agente com agentType no meta (o que o Claude Code grava)."""
        self.agente(sessao, nome, desc)
        meta = os.path.join(self.projects, "proj", sessao, "subagents", "agent-%s.meta.json" % nome)
        with io.open(operarios._long(meta), "w", encoding="utf-8") as f:
            json.dump({"description": desc, "model": "sonnet", "agentType": papel}, f)

    def test_14_subagente_comum_fica_de_fora(self):
        # so subagente do usuario (sem papel orq-* e sem etiqueta): o hook nao pode dizer nada
        self.papel("S", "x1", "Explore code", "Explore")
        self.papel("S", "x2", "pesquisar a doc", "general-purpose")
        p = self.run_in(json.dumps({"session_id": "S"}), "retomar", "--hook")
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "")
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 10)
        # junto com um operario de verdade, so ele conta
        self.agente("S", "a1", "[sonnet:edicao-logica] um")
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ja despachou 1 operario (0 registrados, 1 sem registro).", p.stdout)
        self.assertNotIn("Explore code", p.stdout)
        self.assertNotIn("pesquisar a doc", p.stdout)

    def test_15_papel_orq_conta_mesmo_sem_etiqueta(self):
        self.papel("S", "p1", "ler os logs", "orq-leitor")
        self.papel("S", "p2", "mexer no arquivo", "orquestrador:orq-executor")
        self.papel("S", "p3", "[haiku:busca] achar o simbolo", "general-purpose")
        p = self.run_op("retomar", "--sessao", "S")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ja despachou 3 operarios (0 registrados, 3 sem registro).", p.stdout)

    def test_16_hook_stdin_em_bytes_utf8(self):
        # byte 0x81 (do A com acento em utf-8) nao existe no cp1252: lido como texto no Windows, quebrava
        self.cenario3()
        entrada = json.dumps({"session_id": "S", "cwd": "C:/" + chr(193) + "rea"},
                             ensure_ascii=False).encode("utf-8")
        env = dict(self.env)
        env.pop("PYTHONIOENCODING", None)
        env.pop("PYTHONUTF8", None)
        p = subprocess.run([sys.executable, SCRIPT, "retomar", "--hook"], env=env, input=entrada,
                           capture_output=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn(b"ja despachou 3 operarios", p.stdout)


class TestAtualizacao(Base):
    """Aviso e ligacao da atualizacao automatica. Tudo numa pasta de configuracao falsa
    (ORQ_CLAUDE_DIR), no mesmo formato que o Claude Code grava ao instalar por marketplace."""
    MKT = "loja-teste"

    def setUp(self):
        super(TestAtualizacao, self).setUp()
        self.cfg = os.path.join(self.tmp, "cfg")
        self.raiz = os.path.join(self.cfg, "plugins", "cache", self.MKT, "orquestrador", "abc123")
        os.makedirs(self.raiz)
        self.cwd = os.path.join(self.tmp, "projeto")
        os.makedirs(self.cwd)
        self.settings = os.path.join(self.cfg, "settings.json")
        self.estado = os.path.join(os.path.dirname(self.registro), "atualizacao.json")
        for v in ("DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                  "FORCE_AUTOUPDATE_PLUGINS", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CONFIG_DIR",
                  "ORQ_SEM_AVISO_ATUALIZACAO"):
            self.env.pop(v, None)
        self.env["ORQ_CLAUDE_DIR"] = self.cfg
        self.fonte = {"source": "github", "repo": "alguem/loja-teste"}
        self.json(os.path.join(self.cfg, "plugins", "known_marketplaces.json"),
                  {self.MKT: {"source": self.fonte, "installLocation": "x", "lastUpdated": "2026-01-01T00:00:00Z"}})
        self.json(os.path.join(self.cfg, "plugins", "installed_plugins.json"),
                  {"version": 2, "plugins": {"orquestrador@" + self.MKT: [
                      {"scope": "user", "installPath": self.raiz, "version": "abc123"}]}})
        self.json(self.settings, {"language": "português", "extraKnownMarketplaces": {
            self.MKT: {"source": self.fonte}}, "enabledPlugins": {"orquestrador@" + self.MKT: True}})

    def json(self, caminho, dados, recuo=2):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with io.open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(dados, ensure_ascii=False, indent=recuo) + "\n")

    def at(self, *args, **env):
        e = dict(self.env)
        e.update(env)
        return subprocess.run([sys.executable, SCRIPT, "atualizacao", "--raiz", self.raiz] + list(args),
                              env=e, cwd=self.cwd, capture_output=True, text=True, encoding="utf-8")

    def lido(self, caminho=None):
        with io.open(caminho or self.settings, encoding="utf-8") as f:
            return json.load(f)

    def test_01_copia_solta_nao_tem_o_que_ligar(self):
        solta = os.path.join(self.tmp, "solta")
        os.makedirs(solta)
        p = subprocess.run([sys.executable, SCRIPT, "atualizacao", "--raiz", solta], env=self.env,
                           cwd=self.cwd, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 10, p.stderr)
        self.assertIn("nao veio de um marketplace", p.stdout)
        h = subprocess.run([sys.executable, SCRIPT, "atualizacao", "--hook", "--raiz", solta], env=self.env,
                           cwd=self.cwd, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual((h.returncode, h.stdout, h.stderr), (0, "", ""))
        self.assertFalse(os.path.exists(self.estado))

    def test_02_padrao_desligada(self):
        p = self.at()
        self.assertEqual(p.returncode, 3, p.stderr)
        self.assertIn("marketplace: " + self.MKT, p.stdout)
        self.assertIn("DESLIGADA (padrao)", p.stdout)
        d = json.loads(self.at("--json").stdout)
        self.assertEqual((d["marketplace"], d["ligada"], d["origem"], d["travada_por"]),
                         (self.MKT, False, "padrao", None))

    def test_03_hook_avisa_uma_vez_e_cala(self):
        p = self.at("--hook")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.count("\n"), 1)
        self.assertTrue(p.stdout.startswith("orquestrador: este plugin nao esta recebendo atualizacoes sozinho."))
        self.assertIn("`%s`" % self.MKT, p.stdout)
        self.assertIn("atualizacao --ligar", p.stdout)
        self.assertIn("atualizacao --nao-perguntar", p.stdout)
        self.assertIn("Nao ligue sem a resposta dele.", p.stdout)
        self.assertNotIn("FORCE_AUTOUPDATE_PLUGINS", p.stdout)
        p.stdout.encode("ascii")
        self.assertEqual(self.lido(self.estado)["avisos"], 1)
        self.assertEqual(self.at("--hook").stdout, "")
        self.assertEqual(self.lido(self.settings).get("env"), None, "hook nao pode mexer no settings")
        self.assertNotIn("autoUpdate", self.lido()["extraKnownMarketplaces"][self.MKT])

    def test_04_hook_volta_depois_de_7_dias_e_para_no_terceiro(self):
        velho = (datetime.now().astimezone() - timedelta(days=8)).isoformat(timespec="seconds")
        for n in (1, 2, 3):
            self.assertNotEqual(self.at("--hook").stdout, "", "aviso %d" % n)
            e = self.lido(self.estado)
            self.assertEqual(e["avisos"], n)
            e["ultimo_aviso"] = velho
            self.json(self.estado, e)
        self.assertEqual(self.at("--hook").stdout, "")
        recente = self.lido(self.estado)
        recente["avisos"], recente["ultimo_aviso"] = 1, (datetime.now().astimezone() - timedelta(days=6)).isoformat(timespec="seconds")
        self.json(self.estado, recente)
        self.assertEqual(self.at("--hook").stdout, "", "6 dias ainda e cedo")

    def test_05_nao_perguntar_cala_pra_sempre(self):
        p = self.at("--nao-perguntar")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.at("--hook").stdout, "")
        self.assertTrue(self.lido(self.estado)["recusou"])

    def test_06_ligar_so_acrescenta_a_chave(self):
        antes = self.le(self.settings)
        p = self.at("--ligar")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("atualizacao automatica ligada", p.stdout)
        d = self.lido()
        self.assertIs(d["extraKnownMarketplaces"][self.MKT]["autoUpdate"], True)
        self.assertEqual(d["extraKnownMarketplaces"][self.MKT]["source"], self.fonte)
        self.assertEqual(d["language"], "português")
        self.assertEqual(d["enabledPlugins"], {"orquestrador@" + self.MKT: True})
        self.assertEqual(list(d), ["language", "extraKnownMarketplaces", "enabledPlugins"])
        self.assertNotIn("env", d, "fora do app desktop nao forca nada")
        depois = self.le(self.settings)
        self.assertEqual(depois, antes.replace('"repo": "alguem/loja-teste"\n      }\n',
                                               '"repo": "alguem/loja-teste"\n      },\n      "autoUpdate": true\n'))
        copia = self.le(self.settings + ".antes-do-orquestrador")
        self.assertEqual(copia, antes)
        s = self.at()
        self.assertEqual(s.returncode, 0, s.stdout)
        self.assertIn("LIGADA (settings do usuario)", s.stdout)
        self.assertEqual(self.at("--hook").stdout, "")

    def test_07_ligar_duas_vezes_nao_regrava(self):
        self.at("--ligar")
        m = os.path.getmtime(self.settings)
        os.utime(self.settings, (m - 100, m - 100))
        p = self.at("--ligar")
        self.assertEqual(p.returncode, 0)
        self.assertIn("ja estava ligada", p.stdout)
        self.assertEqual(os.path.getmtime(self.settings), m - 100)

    def test_08_ligar_sem_settings_cria_com_a_fonte(self):
        os.remove(self.settings)
        p = self.at("--ligar")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.lido(), {"extraKnownMarketplaces": {self.MKT: {"source": self.fonte, "autoUpdate": True}}})
        self.assertFalse(os.path.exists(self.settings + ".antes-do-orquestrador"))

    def test_09_settings_quebrado_nao_e_tocado(self):
        for lixo in ('{"a": 1,,}', '[1, 2]', '{"extraKnownMarketplaces": []}',
                     '{"extraKnownMarketplaces": {"loja-teste": "x"}}'):
            with self.subTest(lixo=lixo):
                with io.open(self.settings, "w", encoding="utf-8", newline="") as f:
                    f.write(lixo)
                p = self.at("--ligar")
                self.assertEqual(p.returncode, 13, p.stdout)
                self.assertIn("Nada foi alterado", p.stderr)
                self.assertEqual(self.le(self.settings), lixo)
                self.assertFalse(os.path.exists(self.settings + ".antes-do-orquestrador"))

    def test_10_desligada_de_proposito_o_hook_respeita(self):
        d = self.lido()
        d["extraKnownMarketplaces"][self.MKT]["autoUpdate"] = False
        self.json(self.settings, d)
        self.assertEqual(self.at("--hook").stdout, "")
        self.assertIn("DESLIGADA (settings do usuario)", self.at().stdout)
        self.assertEqual(self.at("--ligar").returncode, 0)  # o usuario pediu agora: liga
        self.assertIs(self.lido()["extraKnownMarketplaces"][self.MKT]["autoUpdate"], True)

    def test_11_botao_do_plugin_conta(self):
        k = os.path.join(self.cfg, "plugins", "known_marketplaces.json")
        d = self.lido(k)
        d[self.MKT]["autoUpdate"] = True
        self.json(k, d)
        s = self.at()
        self.assertEqual(s.returncode, 0, s.stdout)
        self.assertIn("LIGADA (botao do /plugin)", s.stdout)
        self.assertEqual(self.at("--hook").stdout, "")

    def test_12_settings_do_projeto_manda_mais(self):
        self.at("--ligar")
        self.json(os.path.join(self.cwd, ".claude", "settings.json"),
                  {"extraKnownMarketplaces": {self.MKT: {"source": self.fonte, "autoUpdate": False}}})
        s = self.at()
        self.assertEqual(s.returncode, 3)
        self.assertIn("DESLIGADA (settings do projeto)", s.stdout)
        p = self.at("--ligar")
        self.assertIn("continua desligada", p.stdout)
        self.assertEqual(self.at("--hook").stdout, "")

    def test_13_sessao_com_autoupdater_desligado_precisa_do_force(self):
        app = {"DISABLE_AUTOUPDATER": "1"}
        s = self.at(**app)
        self.assertEqual(s.returncode, 3)
        self.assertIn("vem do ambiente da sessao", s.stdout)
        h = self.at("--hook", **app)
        self.assertIn("esta sessao roda com DISABLE_AUTOUPDATER=1", h.stdout)
        self.assertIn("`FORCE_AUTOUPDATE_PLUGINS=1` no bloco `env`", h.stdout)
        p = self.at("--ligar", **app)
        self.assertEqual(p.returncode, 0, p.stderr)
        d = self.lido()
        self.assertIs(d["extraKnownMarketplaces"][self.MKT]["autoUpdate"], True)
        self.assertEqual(d["env"], {"FORCE_AUTOUPDATE_PLUGINS": "1"})
        self.assertIn("vale a partir da proxima sessao", p.stdout)
        # o processo ainda nao tem a variavel (so a proxima sessao tera), mas o settings ja diz
        s = self.at(**app)
        self.assertEqual(s.returncode, 0, s.stdout)
        self.assertEqual(self.at("--hook", **app).stdout, "")

    def test_14_autoupdater_desligado_com_marketplace_ja_ligado(self):
        d = self.lido()
        d["extraKnownMarketplaces"][self.MKT]["autoUpdate"] = True
        d["env"] = {"OUTRA": "x"}
        self.json(self.settings, d)
        app = {"DISABLE_AUTOUPDATER": "1"}
        h = self.at("--hook", **app)
        self.assertIn("ligada, mas esta sessao roda", h.stdout)
        self.assertEqual(self.at("--ligar", **app).returncode, 0)
        self.assertEqual(self.lido()["env"], {"OUTRA": "x", "FORCE_AUTOUPDATE_PLUGINS": "1"})

    def test_15_trava_escolhida_pelo_usuario_e_respeitada(self):
        casos = [{"DISABLE_UPDATES": "1"},
                 {"DISABLE_UPDATES": "1", "DISABLE_AUTOUPDATER": "1"},  # a mais forte manda
                 {"CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}]
        for env in casos:
            with self.subTest(env=sorted(env)):
                self.assertEqual(self.at("--hook", **env).stdout, "")
                self.assertFalse(os.path.exists(self.estado))
        p = self.at("--ligar", DISABLE_UPDATES="1")
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("env", self.lido(), "nao forca por cima da escolha do usuario")
        self.assertIn("desliga toda atualizacao automatica", p.stdout)
        self.assertEqual(self.at(DISABLE_UPDATES="1").returncode, 3)

    def test_16_trava_declarada_no_settings_e_escolha_do_usuario(self):
        d = self.lido()
        d["env"] = {"DISABLE_AUTOUPDATER": "1"}
        self.json(self.settings, d)
        app = {"DISABLE_AUTOUPDATER": "1"}
        self.assertEqual(self.at("--hook", **app).stdout, "")
        self.at("--ligar", **app)
        self.assertEqual(self.lido()["env"], {"DISABLE_AUTOUPDATER": "1"})

    def test_17_force_ja_definido_libera(self):
        env = {"DISABLE_AUTOUPDATER": "1", "FORCE_AUTOUPDATE_PLUGINS": "1"}
        h = self.at("--hook", **env)
        self.assertIn("orquestrador: este plugin nao esta recebendo", h.stdout)
        self.assertNotIn("FORCE_AUTOUPDATE_PLUGINS", h.stdout)

    def test_18_variavel_cala_o_aviso(self):
        self.assertEqual(self.at("--hook", ORQ_SEM_AVISO_ATUALIZACAO="1").stdout, "")
        self.assertFalse(os.path.exists(self.estado))

    def test_19_installed_plugins_atrasado_usa_a_pasta(self):
        self.json(os.path.join(self.cfg, "plugins", "installed_plugins.json"),
                  {"version": 2, "plugins": {"orquestrador@" + self.MKT: [
                      {"scope": "user", "installPath": self.raiz + "-velha", "version": "velha"}]}})
        self.assertIn("marketplace: " + self.MKT, self.at().stdout)

    def test_20_arquivos_ilegiveis_nao_derrubam_o_hook(self):
        for nome in ("installed_plugins.json", "known_marketplaces.json"):
            with io.open(os.path.join(self.cfg, "plugins", nome), "w", encoding="utf-8") as f:
                f.write("{quebrado")
        with io.open(self.settings, "w", encoding="utf-8") as f:
            f.write("{quebrado")
        h = self.at("--hook")
        self.assertEqual((h.returncode, h.stderr), (0, ""))

    def test_21_bom_recuo_e_crlf_preservados(self):
        texto = "﻿" + json.dumps(self.lido(), ensure_ascii=False, indent=4).replace("\n", "\r\n") + "\r\n"
        with io.open(self.settings, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        self.assertIn("DESLIGADA (padrao)", self.at().stdout)
        self.assertEqual(self.at("--ligar").returncode, 0)
        novo = self.le(self.settings)
        self.assertIn('\r\n    "extraKnownMarketplaces"', novo)
        self.assertNotIn("﻿", novo)
        self.assertEqual(novo.count("\n"), novo.count("\r\n"))
        self.assertTrue(json.loads(novo)["extraKnownMarketplaces"][self.MKT]["autoUpdate"])

    def test_22_marketplace_desconhecido_nao_inventa_fonte(self):
        d = self.lido()
        del d["extraKnownMarketplaces"]
        self.json(self.settings, d)
        os.remove(os.path.join(self.cfg, "plugins", "known_marketplaces.json"))
        p = self.at("--ligar")
        self.assertEqual(p.returncode, 13)
        self.assertIn("nao esta cadastrado", p.stderr)
        self.assertNotIn("extraKnownMarketplaces", self.lido())

    def test_23_opcoes_que_nao_combinam(self):
        p = self.at("--ligar", "--nao-perguntar")
        self.assertEqual(p.returncode, 13)
        self.assertFalse(os.path.exists(self.estado))
        self.assertNotIn("autoUpdate", self.lido()["extraKnownMarketplaces"][self.MKT])

    def test_24_env_que_nao_e_objeto_nao_e_tocado(self):
        d = self.lido()
        d["env"] = ["torto"]
        self.json(self.settings, d)
        antes = self.le(self.settings)
        p = self.at("--ligar", DISABLE_AUTOUPDATER="1")
        self.assertEqual(p.returncode, 13, p.stdout)
        self.assertEqual(self.le(self.settings), antes)
        # sem a trava ninguem mexe em `env`: ai liga normalmente
        self.assertEqual(self.at("--ligar").returncode, 0)
        self.assertEqual(self.lido()["env"], ["torto"])

    def test_25_numero_que_nao_cabe_em_json_nao_corrompe(self):
        texto = '{\n  "x": 1e400,\n  "extraKnownMarketplaces": {"%s": {"source": {"source": "github", "repo": "a/b"}}}\n}\n' % self.MKT
        with io.open(self.settings, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        p = self.at("--ligar")
        self.assertEqual(p.returncode, 13, p.stdout)
        self.assertIn("Nada foi alterado", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(self.le(self.settings), texto)
        self.assertFalse(os.path.exists(self.settings + ".antes-do-orquestrador"))

    def test_26_link_simbolico_continua_link(self):
        real = os.path.join(self.tmp, "dotfiles", "settings.json")
        os.makedirs(os.path.dirname(real))
        shutil.move(self.settings, real)
        try:
            os.symlink(real, self.settings)
        except (OSError, NotImplementedError, AttributeError):
            self.skipTest("sem permissao pra criar link simbolico nesta maquina")
        p = self.at("--ligar")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.islink(self.settings), "o link virou arquivo comum")
        self.assertIs(self.lido(real)["extraKnownMarketplaces"][self.MKT]["autoUpdate"], True)

    def test_27_permissao_do_arquivo_e_mantida(self):
        if os.name == "nt":
            self.skipTest("bits de permissao POSIX")
        os.chmod(self.settings, 0o640)
        self.assertEqual(self.at("--ligar").returncode, 0)
        self.assertEqual(os.stat(self.settings).st_mode & 0o777, 0o640)

    def test_28_comando_do_aviso_roda_como_esta(self):
        h = self.at("--hook")
        m = re.search(r"Se sim, rode: (.+?) atualizacao --ligar \(", h.stdout)
        self.assertTrue(m, h.stdout)
        cmd = m.group(1)
        if " " not in sys.executable:
            self.assertFalse(cmd.startswith('"'), "linha que comeca com aspas nao roda no PowerShell")
        # o comando do aviso aponta pro motor de verdade; aqui so se confere que ele existe e responde
        motor = re.search(r'"([^"]+operarios\.py)"', cmd).group(1)
        self.assertTrue(os.path.isfile(motor), motor)


class TestHooksSh(Base):
    """Roda os scripts de hook de verdade, do jeito que o Claude Code chama: sh "<raiz>/hooks/x.sh".
    Sem isto um erro no proprio script passa por todos os testes do motor (ja aconteceu: o corte do
    caminho nao funcionava fora do Windows e o hook ficava calado)."""
    MKT = "loja-teste"

    def setUp(self):
        super(TestHooksSh, self).setUp()
        self.sh = shutil.which("sh")
        if not self.sh:
            self.skipTest("sem sh nesta maquina")
        self.cfg = os.path.join(self.tmp, "cfg")
        self.raiz = os.path.join(self.cfg, "plugins", "cache", self.MKT, "orquestrador", "abc123")
        plugin = os.path.dirname(os.path.dirname(os.path.dirname(AQUI)))
        os.makedirs(os.path.join(self.raiz, "skills", "orquestrador"))
        shutil.copytree(os.path.join(plugin, "hooks"), os.path.join(self.raiz, "hooks"))
        shutil.copy2(SCRIPT, os.path.join(self.raiz, "skills", "orquestrador", "operarios.py"))
        for v in ("DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
                  "FORCE_AUTOUPDATE_PLUGINS", "CLAUDE_CONFIG_DIR", "ORQ_SEM_AVISO_ATUALIZACAO"):
            self.env.pop(v, None)
        self.env["ORQ_CLAUDE_DIR"] = self.cfg
        os.makedirs(os.path.join(self.cfg, "plugins"), exist_ok=True)
        with io.open(os.path.join(self.cfg, "plugins", "installed_plugins.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 2, "plugins": {"orquestrador@" + self.MKT: [
                {"scope": "user", "installPath": self.raiz, "version": "abc123"}]}}, f)

    def hook(self, nome, entrada=""):
        script = self.raiz.replace("\\", "/") + "/hooks/" + nome
        return subprocess.run([self.sh, script], env=self.env, cwd=self.tmp, input=entrada,
                              capture_output=True, text=True, encoding="utf-8", timeout=120)

    def test_1_atualizacao_sh_chega_no_motor(self):
        p = self.hook("atualizacao.sh")
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertTrue(p.stdout.startswith("orquestrador: este plugin nao esta recebendo atualizacoes sozinho."),
                        "o script nao chegou no motor: %r" % p.stdout)
        self.assertIn("`%s`" % self.MKT, p.stdout)
        self.assertEqual(self.hook("atualizacao.sh").stdout, "", "segundo aviso na mesma semana")

    def test_2_retomar_sh_chega_no_motor(self):
        sub = os.path.join(self.projects, "proj", "S", "subagents")
        os.makedirs(sub)
        with io.open(os.path.join(sub, "agent-a1.meta.json"), "w", encoding="utf-8") as f:
            json.dump({"description": "[sonnet:edicao-logica] um", "model": "sonnet"}, f)
        with io.open(os.path.join(sub, "agent-a1.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "m1", "model": "claude-sonnet-5-5", "usage": {"output_tokens": 10}}}) + "\n")
        p = self.hook("retomar.sh", json.dumps({"session_id": "S", "source": "compact"}))
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertTrue(p.stdout.startswith("orquestrador: esta sessao ja despachou 1 operario"),
                        "o script nao chegou no motor: %r" % p.stdout)

    def test_3_sem_nada_a_dizer_ficam_calados(self):
        p = self.hook("retomar.sh", json.dumps({"session_id": "vazia"}))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))
        self.env["ORQ_SEM_AVISO_ATUALIZACAO"] = "1"
        p = self.hook("atualizacao.sh")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def entrada_agent(self, desc, papel, model=None, prompt="x"):
        ti = {"description": desc, "prompt": prompt, "subagent_type": papel}
        if model:
            ti["model"] = model
        return json.dumps({"session_id": "S", "hook_event_name": "PreToolUse", "tool_name": "Agent",
                           "tool_input": ti})

    def test_4_despacho_sh_avisa_sem_bloquear(self):
        p = self.hook("despacho.sh", self.entrada_agent("cartao", "orquestrador:orq-executor"))
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        o = json.loads(p.stdout)
        self.assertEqual(list(o), ["hookSpecificOutput"], "so contexto: nada de decisao de permissao")
        h = o["hookSpecificOutput"]
        self.assertEqual(sorted(h), ["additionalContext", "hookEventName"])
        self.assertEqual(h["hookEventName"], "PreToolUse")
        for trecho in ("nao bloqueia", "sem model", "descricao sem [modelo:tipo]", "brief sem ACEITE"):
            self.assertIn(trecho, h["additionalContext"])

    def test_5_despacho_sh_calado_fora_da_skill(self):
        certo = self.entrada_agent("[sonnet:front] cartao", "orq-executor", "sonnet", "OBJETIVO x ACEITE: y")
        for entrada in (self.entrada_agent("Explore the repo", "Explore"),
                        self.entrada_agent("Pesquisar precos [rascunho]", "general-purpose", "opus"),
                        self.entrada_agent("ler a pasta docs", "claude"),
                        certo, "", "{quebrado orq-"):
            p = self.hook("despacho.sh", entrada)
            self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""), entrada)

    def test_6_despacho_sh_nem_chama_o_motor_fora_da_skill(self):
        # motor trocado por um que sempre fala: agente comum nao pode chegar nele
        with io.open(os.path.join(self.raiz, "skills", "orquestrador", "operarios.py"), "w",
                     encoding="utf-8") as f:
            f.write('print(\'{"chamou": 1}\')\n')
        p = self.hook("despacho.sh", self.entrada_agent("Explore the repo", "Explore"))
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        p = self.hook("despacho.sh", self.entrada_agent("cartao", "orq-executor"))
        self.assertEqual((p.returncode, p.stdout.strip()), (0, '{"chamou": 1}'))

    def test_6b_despacho_sh_so_repassa_json(self):
        # interpretador que sai 0 dizendo outra coisa (atalho de loja, aviso de versao) nao vira contexto
        with io.open(os.path.join(self.raiz, "skills", "orquestrador", "operarios.py"), "w",
                     encoding="utf-8") as f:
            f.write('print("Python was not found; run without arguments to install")\n')
        p = self.hook("despacho.sh", self.entrada_agent("cartao", "orq-executor"))
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "", ""))

    def test_7_despacho_sh_sem_motor_fica_calado(self):
        os.remove(os.path.join(self.raiz, "skills", "orquestrador", "operarios.py"))
        p = self.hook("despacho.sh", self.entrada_agent("cartao", "orq-executor"))
        self.assertEqual((p.returncode, p.stdout), (0, ""))


class TestClasseObrigatoria(Base):
    def regs_args(self, *erros):
        a = ["registrar", "--tipo", "teste", "--modelo", "sonnet", "--resultado", "corrigido",
             "--rodadas", "1", "--brief", "2"]
        for e in erros:
            a += ["--erro", e]
        return a

    def test_tabela_classe_do_erro(self):
        casos = [
            ("estado: fechou so a entrada", ("estado", "fechou so a entrada")),
            ("Escopo-incompleto: moldura so no chefe", ("escopo", "moldura so no chefe")),
            ("teste_fraco: a prova passava sem a mudanca",
             ("teste", "a prova passava sem a mudanca")),
            # frase comum que comeca com nome de classe NAO vira classe por acidente
            ("teste de carga falhou: timeout", (None, "teste de carga falhou: timeout")),
            ("Estado do banco: travado", (None, "Estado do banco: travado")),
            ("segurança: log com dado pessoal", ("seguranca", "log com dado pessoal")),
            ("alegação : disse feito", ("alegacao", "disse feito")),
            ("outro: nao coube", ("outro", "nao coube")),
            ("estado:", ("estado", "estado:")),
            ("texto sem classe", (None, "texto sem classe")),
            ("painel: montava texto a cada quadro", (None, "painel: montava texto a cada quadro")),
        ]
        for entrada, saida in casos:
            self.assertEqual(operarios._classe_do_erro(entrada), saida, entrada)

    def test_recusa_sem_gravar(self):
        p = self.run_op(*self.regs_args("estado: ok", "sem classe aqui"))
        self.assertEqual(p.returncode, 13)
        self.assertIn('--erro sem classe: "sem classe aqui"', p.stderr)
        self.assertIn("Nada foi gravado.", p.stderr)
        self.assertFalse(os.path.exists(self.registro))

    def test_aviso_ponto_e_virgula(self):
        p = self.run_op(*self.regs_args("estado: a; b"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr.count("parece juntar mais de um erro"), 1)

    def test_listar(self):
        p = self.run_op("reclassificar", "--listar")
        self.assertEqual(p.returncode, 10)
        self.assertIn("nenhum erro sem classe", p.stdout)
        self.grava("teste", "sonnet", "corrigido", id="abc12345", erros=["x", "y"],
                   classes=["estado", "outro"])
        self.grava("teste", "sonnet", "corrigido", id="def67890", erros=["z"], classes=["estado"])
        p = self.run_op("reclassificar", "--listar")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("abc12345", p.stdout)
        self.assertIn("  [2] outro: y", p.stdout)
        self.assertNotIn("def67890", p.stdout)

    def test_id_certo(self):
        self.grava("teste", "sonnet", "corrigido", id="aaaa1111", erros=["a"], classes=["estado"])
        with io.open(self.registro, "a", encoding="utf-8", newline="") as f:
            f.write("{quebrada\n")
        self.grava("teste", "sonnet", "corrigido", id="abc12345", erros=["x", "y"],
                   classes=["outro", "outro"])
        self.grava("teste", "sonnet", "corrigido", id="bbbb2222", erros=["b"], classes=["borda"])
        antes = self.le(self.registro)
        p = self.run_op("reclassificar", "--id", "abc12345", "--classe", "escopo", "--classe", "borda")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("  [1] escopo: x", p.stdout)
        self.assertIn("  [2] borda: y", p.stdout)
        self.assertEqual(self.le(self.registro + ".antes-de-reclassificar"), antes)
        la, lb = antes.splitlines(True), self.le(self.registro).splitlines(True)
        self.assertEqual(len(la), len(lb))
        for i, (x, y) in enumerate(zip(la, lb)):
            if '"abc12345"' in x:
                self.assertEqual(json.loads(y)["classes"], ["escopo", "borda"])
            else:
                self.assertEqual(x, y)
        self.assertEqual(lb[1], "{quebrada\n")

    def test_crlf_bom_e_fim_sem_quebra_ficam_como_estavam(self):
        l1 = json.dumps({"ts": "2026-01-01T10:00:00-03:00", "id": "aaaa1111", "tipo": "teste",
                         "modelo": "sonnet", "resultado": "corrigido", "rodadas": 1, "brief": 3,
                         "erros": ["a"], "classes": ["outro"]})
        l2 = json.dumps({"ts": "2026-01-01T10:00:00-03:00", "id": "bbbb2222", "tipo": "teste",
                         "modelo": "sonnet", "resultado": "corrigido", "rodadas": 1, "brief": 3,
                         "erros": ["b"], "classes": ["outro"]})
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        # BOM no comeco, CRLF nas linhas, lixo no meio e a ultima linha SEM quebra
        with io.open(self.registro, "wb") as f:
            f.write(b"\xef\xbb\xbf" + l1.encode("utf-8") + b"\r\n{quebrada\r\n" + l2.encode("utf-8"))
        p = self.run_op("reclassificar", "--id", "bbbb2222", "--classe", "borda")
        self.assertEqual(p.returncode, 0, p.stderr)
        with io.open(self.registro, "rb") as f:
            depois = f.read()
        partes = depois.split(b"\r\n")
        self.assertEqual(len(partes), 3, depois)
        self.assertEqual(partes[0], l1.encode("utf-8"))        # so o BOM sai
        self.assertEqual(partes[1], b"{quebrada")
        self.assertEqual(json.loads(partes[2].decode("utf-8"))["classes"], ["borda"])
        self.assertFalse(depois.endswith(b"\n"), "ganhou quebra de linha no fim")
        p = self.run_op("reclassificar", "--id", "aaaa1111", "--classe", "estado")
        self.assertEqual(p.returncode, 0, p.stderr)
        with io.open(self.registro, "rb") as f:
            self.assertEqual(f.read().count(b"\r\n"), 2)

    def test_byte_invalido_nao_altera_nada(self):
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        bruto = b'{"id": "aaaa1111", "erros": ["a"]}\n\xff\xfe lixo\n'
        with io.open(self.registro, "wb") as f:
            f.write(bruto)
        p = self.run_op("reclassificar", "--id", "aaaa1111", "--classe", "estado")
        self.assertEqual(p.returncode, 13, p.stdout)
        self.assertIn("Nada foi alterado", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        with io.open(self.registro, "rb") as f:
            self.assertEqual(f.read(), bruto)

    def test_quantidade_errada(self):
        self.grava("teste", "sonnet", "corrigido", id="abc12345", erros=["x", "y"],
                   classes=["outro", "outro"])
        antes = self.le(self.registro)
        p = self.run_op("reclassificar", "--id", "abc12345", "--classe", "escopo")
        self.assertEqual(p.returncode, 13)
        self.assertIn("o registro tem 2 erro(s) e vieram 1 classe(s):", p.stderr)
        self.assertEqual(self.le(self.registro), antes)

    def test_id_inexistente_e_sem_classe(self):
        self.grava("teste", "sonnet", "corrigido", id="abc12345", erros=["x"])
        p = self.run_op("reclassificar", "--id", "nao", "--classe", "escopo")
        self.assertEqual(p.returncode, 13)
        self.assertIn("id nao encontrado: nao", p.stderr)
        p = self.run_op("reclassificar", "--id", "abc12345")
        self.assertEqual(p.returncode, 13)
        self.assertIn("--id exige ao menos um --classe", p.stderr)

    def test_registro_antigo_sem_classes(self):
        self.grava("teste", "sonnet", "corrigido", id="abc12345", erros=["x"])
        p = self.run_op("reclassificar", "--id", "abc12345", "--classe", "teste")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(self.le(self.registro).splitlines()[0])["classes"], ["teste"])


class TestPrimeiraEntrega(Base):
    DESC = "[sonnet:edicao-mecanica] tarefa de teste"

    def agente(self, eventos, nome="pe1", desc=None, modelo="claude-sonnet-5-5"):
        """eventos: ("u", texto|lista) | ("t",) tool_result | ("a", id) resposta | ("a",) sem id."""
        sub = os.path.join(self.projects, "proj", "sess1", "subagents")
        os.makedirs(operarios._long(sub), exist_ok=True)
        mp = os.path.join(sub, "agent-%s.meta.json" % nome)
        with io.open(operarios._long(mp), "w", encoding="utf-8") as f:
            json.dump({"description": desc or self.DESC, "model": "sonnet"}, f)
        with io.open(operarios._long(os.path.join(sub, "agent-%s.jsonl" % nome)), "w",
                     encoding="utf-8") as f:
            for e in eventos:
                if e[0] == "u":
                    d = {"type": "user", "message": {"role": "user", "content": e[1]}}
                elif e[0] == "t":
                    d = {"type": "user", "message": {"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": "x", "content": "ok"}]}}
                else:
                    m = {"model": modelo, "usage": {"output_tokens": 10, "input_tokens": 5}}
                    if len(e) > 1:
                        m["id"] = e[1]
                    d = {"type": "assistant", "message": m}
                f.write(json.dumps(d) + "\n")
        return mp

    def an(self, eventos):
        i = operarios.analisar_agente(self.agente(eventos))
        return i["respostas"], i["respostas_1a"]

    def test_tabela_analisar_agente(self):
        B = ("u", "brief")
        A = lambda n: [("a",)] * n  # noqa: E731
        self.assertEqual(self.an([B] + A(3)), (3, 3))
        self.assertEqual(self.an([B] + A(2) + [("t",)] + A(1)), (3, 3))
        self.assertEqual(self.an([B] + A(2) + [("u", "corrija X")] + A(2)), (4, 2))
        self.assertEqual(self.an([B, ("u", "<system-reminder> Your final report...")] + A(3)), (3, 3))
        self.assertEqual(self.an(
            [B] + A(2) + [("u", [{"type": "text", "text": "The coordinator sent a message while "
                                                          "you were working: x"}])]
            + A(1) + [("u", "outra")] + A(1)), (4, 2))
        self.assertEqual(self.an([B, ("a", "m1"), ("a", "m1"), ("u", "corrija"), ("a", "m2")]), (2, 1))
        i = operarios.analisar_agente(os.path.join(self.tmp, "nada.meta.json"))
        self.assertEqual((i["respostas"], i["respostas_1a"]), (0, 0))

    def test_prefixos_harness_e_tool_result_misto(self):
        B = ("u", "brief")
        for pref in ("[handback-send-enforce] x", "[Image: a.png]", "This session is being continued x"):
            self.assertEqual(self.an([B, ("a",), ("u", pref), ("a",)]), (2, 2), pref)
        misto = ("u", [{"type": "text", "text": "x"}, {"type": "tool_result", "content": "y"}])
        self.assertEqual(self.an([B, ("a",), misto, ("a",)]), (2, 2))
        self.assertEqual(self.an([B, ("a",), ("u", ""), ("a",)]), (2, 2))

    def registra(self, eventos, resultado, rodadas, *extra, desc=None, nome="pe1"):
        self.agente(eventos, nome=nome, desc=desc)
        return self.run_op("registrar", "--agente", desc or self.DESC, "--resultado", resultado,
                           "--rodadas", str(rodadas), "--brief", "2", *extra)

    def ultimo(self):
        with io.open(self.registro, encoding="utf-8") as f:
            return json.loads(f.read().strip().splitlines()[-1])

    def test_registrar_respostas_1a_tres_ramos(self):
        B = ("u", "brief")
        p = self.registra([B] + [("a",)] * 4, "de_primeira", 0)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.ultimo()["respostas_1a"], 4)
        p = self.registra([B] + [("a",)] * 4 + [("u", "corrija")] + [("a",)] * 2, "corrigido", 1,
                          "--licao", "x")
        self.assertEqual(p.returncode, 0, p.stderr)
        r = self.ultimo()
        self.assertEqual((r["respostas"], r["respostas_1a"]), (6, 4))
        p = self.registra([B] + [("a",)] * 4, "corrigido", 1, "--licao", "x")
        self.assertEqual(p.returncode, 0, p.stderr)
        r = self.ultimo()
        self.assertEqual(r["respostas"], 4)
        self.assertNotIn("respostas_1a", r)

    def rev(self, *extra, tipo="revisao"):
        return self.run_op("registrar", "--tipo", tipo, "--modelo", "sonnet", "--resultado",
                           "de_primeira", "--rodadas", "0", "--brief", "2", *extra)

    def test_placar_revisao(self):
        casos = [
            (("--achados", "3"), "debug", "so valem para revisao"),
            (("--confirmados", "1", "--achados", "3"), "texto", "so valem para revisao"),
            (("--achados", "-1"), "revisao", "nao podem ser negativos"),
            (("--achados", "3", "--confirmados", "-2"), "revisao", "nao podem ser negativos"),
            (("--confirmados", "1"), "revisao", "--confirmados exige --achados"),
            (("--achados", "2", "--confirmados", "3"), "revisao", "nao pode passar de --achados"),
        ]
        for extra, tipo, msg in casos:
            p = self.rev(*extra, tipo=tipo)
            self.assertEqual(p.returncode, 13, (extra, p.stderr))
            self.assertIn("erro: ", p.stderr)
            self.assertIn(msg, p.stderr)
            self.assertFalse(os.path.exists(self.registro), extra)
        p = self.rev("--achados", "5", "--confirmados", "2")
        self.assertEqual(p.returncode, 0, p.stderr)
        r = self.ultimo()
        self.assertEqual((r["achados"], r["confirmados"]), (5, 2))
        p = self.rev("--achados", "4")
        r = self.ultimo()
        self.assertEqual(r["achados"], 4)
        self.assertNotIn("confirmados", r)

    def test_placar_tipo_vem_do_agente(self):
        p = self.registra([("u", "b"), ("a",)], "de_primeira", 0, "--achados", "1")
        self.assertEqual(p.returncode, 13)
        self.assertIn("so valem para revisao", p.stderr)
        p = self.registra([("u", "b"), ("a",)], "de_primeira", 0, "--achados", "1",
                          desc="[sonnet:revisao] rever", nome="pe2")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.ultimo()["achados"], 1)

    def grande(self, resultado, rodadas, *extra, desc=None):
        ev = [("u", "b")] + [("a",)] * 31
        if rodadas:
            ev += [("u", "corrija")] + [("a",)] * 2
        return self.registra(ev, resultado, rodadas, *extra, desc=desc)

    def test_aviso_a_tarefa_grande(self):
        for res in ("corrigido", "escalado", "falhou"):
            p = self.grande(res, 1, "--licao", "x")
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("AVISO: tarefa grande (31 respostas ate a 1a entrega; a partir de 30", p.stderr)
            self.assertIn("Na proxima: um objetivo por tarefa.", p.stderr)
        p = self.grande("de_primeira", 0)
        self.assertNotIn("tarefa grande", p.stderr)
        p = self.grande("corrigido", 1, "--licao", "x", desc="[sonnet:leitura] ler")
        self.assertNotIn("tarefa grande", p.stderr)
        # abaixo do limite
        p = self.registra([("u", "b")] + [("a",)] * 29 + [("u", "c")] + [("a",)], "corrigido", 1,
                          "--licao", "x")
        self.assertNotIn("tarefa grande", p.stderr)

    def test_aviso_b_tarefa_pequena(self):
        ev = [("u", "b")] + [("a",)] * 5
        p = self.registra(ev, "de_primeira", 0)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("AVISO: tarefa pequena (5 respostas) de primeira em sonnet: a proxima parecida "
                      "de edicao-mecanica vale o experimento em haiku brief 3 (feitos 0 de 4), "
                      "registrando com --experimento.", p.stderr)
        # com --experimento
        p = self.registra(ev, "de_primeira", 0, "--experimento")
        self.assertNotIn("tarefa pequena", p.stderr)
        # 20 respostas
        p = self.registra([("u", "b")] + [("a",)] * 20, "de_primeira", 0)
        self.assertNotIn("tarefa pequena", p.stderr)
        # ficha sem experimento pro tipo (debug nao tem modelo barato)
        p = self.registra(ev, "de_primeira", 0, desc="[sonnet:debug] achar bug")
        self.assertNotIn("tarefa pequena", p.stderr)
        # tipo que nao e de escrita
        p = self.registra(ev, "de_primeira", 0, desc="[sonnet:leitura] ler")
        self.assertNotIn("tarefa pequena", p.stderr)
        # sem --agente nao ha respostas_1a
        p = self.run_op("registrar", "--tipo", "edicao-mecanica", "--modelo", "sonnet",
                        "--resultado", "de_primeira", "--rodadas", "0", "--brief", "2")
        self.assertNotIn("tarefa pequena", p.stderr)

    def test_aviso_c_sem_erro_e_sem_licao(self):
        for res in ("corrigido", "escalado", "falhou"):
            p = self.reg_sem("edicao-mecanica", res)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("AVISO: %s sem --erro e sem --licao: a ficha nao aprende com esta linha."
                          % res, p.stderr)
            self.assertIn('--erro "classe: detalhe"; faltou no brief = --licao.', p.stderr)
        p = self.reg_sem("edicao-mecanica", "corrigido", "--licao", "faltou X")
        self.assertNotIn("sem --erro e sem --licao", p.stderr)
        p = self.reg_sem("edicao-mecanica", "corrigido", "--erro", "outro: y")
        self.assertNotIn("sem --erro e sem --licao", p.stderr)
        p = self.reg_sem("edicao-mecanica", "de_primeira")
        self.assertNotIn("sem --erro e sem --licao", p.stderr)

    def reg_sem(self, tipo, res, *extra):
        rod = "0" if res == "de_primeira" else "1"
        return self.run_op("registrar", "--tipo", tipo, "--modelo", "sonnet", "--resultado", res,
                           "--rodadas", rod, "--brief", "2", *extra)

    def test_aviso_nao_muda_stdout(self):
        p = self.reg_sem("edicao-mecanica", "corrigido")
        self.assertEqual(len(p.stdout.strip().splitlines()), 1)
        json.loads(p.stdout)


class TestFichaUsoReal(Base):
    T = "edicao-logica"

    def limpa(self):
        if os.path.exists(self.registro):
            os.remove(self.registro)

    def rota(self, tipo=None):
        return self.ficha_json(tipo or self.T)

    # ---- passo 2 (A)
    def test_a_so_falta_de_brief_nao_pune(self):
        self.grava(self.T, "sonnet", "de_primeira", brief=3)
        self.grava(self.T, "sonnet", "corrigido", n=3, brief=3, erros=[], licao="faltou o grep")
        self.grava(self.T, "sonnet", "falhou", brief=3, erros=["x"])
        r = self.rota()
        self.assertEqual((r["modelo"], r["brief"], r["effort"]), ("sonnet", 3, None))
        self.assertEqual(r["stats"]["sonnet"]["do_brief"], 3)

    def test_a_falha_de_verdade_nao_e_diluida_pelo_brief(self):
        # 2 de primeira + 2 escalado: metade das entregas julgaveis falhou. As 4 rodadas do brief
        # nao podem esconder isso (sem elas o balde seria "nao da": ok 2/4 < 60%).
        self.grava(self.T, "sonnet", "de_primeira", n=2, brief=3)
        self.grava(self.T, "sonnet", "escalado", n=2, brief=3, erros=["x"])
        self.grava(self.T, "sonnet", "corrigido", n=4, brief=3, erros=[], licao="faltou o grep")
        com = self.rota()
        self.limpa()
        self.grava(self.T, "sonnet", "de_primeira", n=2, brief=3)
        self.grava(self.T, "sonnet", "escalado", n=2, brief=3, erros=["x"])
        sem = self.rota()
        self.assertEqual((com["modelo"], com["brief"], com["effort"]),
                         (sem["modelo"], sem["brief"], sem["effort"]))
        self.assertNotEqual(com["modelo"], "sonnet", com["motivo"])

    def test_a_tres_falhas_seguidas_continuam_duras_com_brief_no_meio(self):
        self.grava(self.T, "sonnet", "falhou", n=2, brief=3, erros=["x"])
        self.grava(self.T, "sonnet", "corrigido", n=1, brief=3, erros=[], licao="faltou o grep")
        self.grava(self.T, "sonnet", "falhou", n=1, brief=3, erros=["x"])
        self.assertNotEqual(self.rota()["modelo"], "sonnet")

    def test_f_classe_mais_comum_no_tipo_soma_os_modelos(self):
        # 2 em opus + 1 em sonnet: nenhum par tem 2 da mesma classe na rota, mas o TIPO tem 3
        self.grava(self.T, "opus", "corrigido", n=2, brief=3, erros=["a"], classes=["estado"])
        self.grava(self.T, "sonnet", "corrigido", n=1, brief=3, erros=["b"], classes=["estado"])
        self.grava(self.T, "sonnet", "corrigido", n=1, brief=3, erros=["c"], classes=["outro"])
        av = self.rota()["avisos"]
        self.assertEqual([a for a in av if a.startswith("no tipo:")],
                         ["no tipo: 3 de 4 entregas com erro foram de estado, somando os modelos -> no brief: "
                          "a ordem dos eventos e o que acontece ao repetir, cancelar, recarregar"])

    def test_f_classe_do_tipo_precisa_de_tres_e_nao_repete_o_aviso_do_par(self):
        self.grava(self.T, "opus", "corrigido", n=2, brief=3, erros=["a"], classes=["estado"])
        self.assertFalse(any(a.startswith("no tipo:") for a in self.rota()["avisos"]))
        self.limpa()
        self.grava(self.T, "sonnet", "corrigido", n=3, brief=3, erros=["a"], classes=["estado"])
        av = self.rota()["avisos"]
        self.assertTrue(any(a.startswith("cuidado: 3 de 3 entregas com erro foram de estado") for a in av), av)
        self.assertFalse(any(a.startswith("no tipo:") for a in av), av)

    def test_a_corrigido_com_erro_pune(self):
        self.grava(self.T, "sonnet", "de_primeira", brief=3)
        self.grava(self.T, "sonnet", "corrigido", n=4, brief=3, erros=["x"], licao="l")
        r = self.rota()
        self.assertEqual((r["modelo"], r["effort"]), ("sonnet", "high"))
        self.assertIn("de primeira 1/5", r["motivo"])

    def test_a_corrigido_sem_erro_sem_licao_pune(self):
        self.grava(self.T, "sonnet", "de_primeira", brief=3)
        self.grava(self.T, "sonnet", "corrigido", n=4, brief=3, erros=[], licao="")
        r = self.rota()
        self.assertEqual(r["effort"], "high")
        self.assertEqual(r["stats"]["sonnet"]["do_brief"], 0)

    def test_a_mistura_vira_bom(self):
        self.grava(self.T, "sonnet", "de_primeira", n=2, brief=3)
        self.grava(self.T, "sonnet", "corrigido", n=2, brief=3, erros=["x"])
        self.grava(self.T, "sonnet", "corrigido", n=3, brief=3, erros=[], licao="faltou")
        r = self.rota()
        self.assertEqual((r["modelo"], r["brief"], r["effort"]), ("sonnet", 3, None))
        self.assertEqual(r["motivo"], "rota padrao")

    def test_a_quatro_falhou_nao_da(self):
        self.grava(self.T, "sonnet", "falhou", n=4, brief=3, erros=["x"])
        r = self.rota()
        self.assertNotEqual(r["modelo"], "sonnet")

    # ---- passo 3 (B)
    def test_b_faltou_no_brief_e_licao_separada(self):
        self.grava(self.T, "sonnet", "corrigido", brief=3, erros=[], licao="Faltou A")
        self.grava(self.T, "sonnet", "corrigido", brief=3, erros=[], licao="faltou a")
        self.grava(self.T, "sonnet", "corrigido", brief=3, erros=[], licao="faltou B")
        self.grava(self.T, "sonnet", "corrigido", brief=3, erros=[], licao="faltou C")
        self.grava(self.T, "sonnet", "de_primeira", brief=3, licao="boa pratica")
        r = self.rota()
        self.assertEqual(r["faltou"], ["faltou C", "faltou B"])
        self.assertEqual(r["do_brief"], [4, 5])
        self.assertEqual(r["licoes"], ["boa pratica"])
        p = self.run_op("ficha", "--tipo", self.T)
        self.assertIn("  brief: 4 das ultimas 5 entregas voltaram por falta no brief "
                      "(nao conta contra o modelo)", p.stdout)
        self.assertIn("  faltou no brief: faltou C", p.stdout)
        self.assertIn("  licao: boa pratica", p.stdout)
        self.assertNotIn("licao: faltou", p.stdout)

    def test_b_uma_so_nao_mostra_linha_brief(self):
        self.grava(self.T, "sonnet", "corrigido", brief=3, erros=[], licao="faltou A")
        p = self.run_op("ficha", "--tipo", self.T)
        self.assertNotIn("  brief:", p.stdout)
        self.assertIn("faltou no brief: faltou A", p.stdout)

    def test_b_secao_na_nota(self):
        self.grava("busca", "haiku", "de_primeira", licao="grep")
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        t = self.le(self.ficha)
        self.assertNotIn("## O que faltou no brief", t)
        self.grava(self.T, "sonnet", "corrigido", brief=3, erros=[], licao="faltou o contrato")
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        t = self.le(self.ficha)
        i = t.find("## O que faltou no brief")
        self.assertTrue(t.find("## O que funciona") < i < t.find("## Exemplos de brief"))
        self.assertIn("### edicao-logica (sonnet)\n- faltou o contrato", t)

    # ---- passo 4 (C)
    def _regs(self, tipo, resultado, resp, n):
        return [{"tipo": tipo, "resultado": resultado, "respostas_1a": resp} for _ in range(n)]

    def test_c_tabela(self):
        f = operarios.tamanho_geral
        regs = (self._regs(self.T, "de_primeira", 10, 7) + self._regs(self.T, "corrigido", 10, 1)
                + self._regs(self.T, "de_primeira", 40, 3) + self._regs(self.T, "corrigido", 40, 5))
        t = f(regs)
        self.assertEqual(t, {"corte": 30, "peq": [7, 8], "gra": [3, 8]})
        self.assertIn("menos de 30 respostas passa de primeira 7/8; com 30 ou mais, 3/8",
                      operarios.texto_tamanho(t))
        self.assertIsNone(f(self._regs(self.T, "corrigido", 10, 8) + self._regs(self.T, "corrigido", 40, 7)))
        regs = (self._regs(self.T, "de_primeira", 10, 6) + self._regs(self.T, "corrigido", 10, 2)
                + self._regs(self.T, "de_primeira", 40, 5) + self._regs(self.T, "corrigido", 40, 3))
        self.assertIsNone(f(regs))

    def test_c_registros_que_nao_entram(self):
        f = operarios.tamanho_geral
        regs = (self._regs(self.T, "de_primeira", 10, 8) + self._regs(self.T, "corrigido", 40, 8))
        self.assertIsNotNone(f(regs))
        ruido = (self._regs(self.T, "corrigido", None, 20) + self._regs(self.T, "corrigido", True, 20)
                 + self._regs("leitura", "corrigido", 40, 20) + self._regs(self.T, "anulado", 40, 20))
        for r in ruido:
            if r["respostas_1a"] is None:
                del r["respostas_1a"]
        self.assertEqual(f(regs + ruido), f(regs))
        self.assertIsNone(f(ruido))

    def test_c_ficha_texto_json_e_nota(self):
        self.grava(self.T, "sonnet", "de_primeira", n=7, respostas_1a=10)
        self.grava(self.T, "sonnet", "corrigido", n=1, respostas_1a=10, erros=["x"])
        self.grava(self.T, "sonnet", "de_primeira", n=3, respostas_1a=40)
        self.grava(self.T, "sonnet", "corrigido", n=5, respostas_1a=40, erros=["x"])
        p = self.run_op("ficha")
        self.assertTrue(p.stdout.startswith("tamanho: escrita que o operario fecha em menos de 30"))
        p = self.run_op("ficha", "--tipo", self.T)
        self.assertTrue(p.stdout.startswith("tamanho:"))
        p = self.run_op("ficha", "--tipo", "busca")
        self.assertNotIn("tamanho:", p.stdout)
        p = self.run_op("ficha", "--json")
        self.assertIsInstance(json.loads(p.stdout), list)
        self.run_op("atualizar")
        t = self.le(self.ficha)
        self.assertRegex(t, r"registros\.\n\ntamanho: .*\n\n\| tipo")

    # ---- passo 5 (D)
    def test_d_placar(self):
        self.grava("revisao", "sonnet", "de_primeira", n=3, achados=3, confirmados=2)
        self.grava("revisao", "sonnet", "de_primeira", achados=True, confirmados=True)
        self.grava("revisao", "sonnet", "de_primeira", achados=5)
        r = self.rota("revisao")
        self.assertEqual(r["stats"]["sonnet"]["placar"], [3, 9, 6])
        p = self.run_op("ficha", "--tipo", "revisao")
        self.assertIn("achados 9 confirmados 6 em 3 revisoes", p.stdout)

    def test_d_sem_placar(self):
        self.grava("revisao", "sonnet", "de_primeira", n=2)
        r = self.rota("revisao")
        self.assertEqual(r["stats"]["sonnet"]["placar"][0], 0)
        p = self.run_op("ficha", "--tipo", "revisao")
        self.assertNotIn("achados", p.stdout)

    # ---- passo 6 (E)
    def test_e_resumo_partes(self):
        self.grava("busca", "haiku", "de_primeira")
        p = self.run_op("resumo", "--todas")
        self.assertNotIn("em execucao", p.stdout)
        self.assertNotIn("grandes:", p.stdout)
        self.limpa()
        self.grava(self.T, "opus", "de_primeira", tokens_saida=1500000, tokens_v=2)
        self.grava(self.T, "opus", "corrigido", erros=["x"])
        self.grava("texto", "fable", "de_primeira")
        self.grava("revisao", "opus", "de_primeira")
        self.grava(self.T, "opus", "anulado")
        p = self.run_op("resumo", "--todas")
        self.assertIn("haiku fez 0 de 4 | opus+fable em execucao: 3 tarefas, 1,5M de saida, 2 de primeira",
                      p.stdout)
        self.limpa()
        self.grava(self.T, "opus", "de_primeira")
        p = self.run_op("resumo", "--todas")
        self.assertIn("opus em execucao: 1 tarefas, - de saida, 1 de primeira", p.stdout)

    def test_e_resumo_grandes(self):
        self.grava(self.T, "sonnet", "de_primeira", n=2, respostas_1a=40)
        self.grava(self.T, "sonnet", "corrigido", respostas_1a=30)
        self.grava(self.T, "sonnet", "de_primeira", n=3, respostas_1a=5)
        self.grava(self.T, "sonnet", "de_primeira", respostas_1a=True)
        self.grava("busca", "haiku", "de_primeira", respostas_1a=99)
        p = self.run_op("resumo", "--todas")
        self.assertIn("grandes: 3 de 6 de escrita, 2 de primeira", p.stdout)


class TestDespacho(Base):
    def desp(self, desc, st="orq-executor", model="sonnet", prompt="OBJETIVO: x ACEITE: npm test",
             sid=None, tool="Agent", hook=True, env_extra=None):
        ti = {"description": desc, "prompt": prompt, "subagent_type": st}
        if model is not None:
            ti["model"] = model
        d = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": ti}
        if sid:
            d["session_id"] = sid
        return self.bruto(json.dumps(d), hook=hook, env_extra=env_extra)

    def bruto(self, texto, hook=True, env_extra=None):
        env = dict(self.env)
        env.update(env_extra or {})
        a = [sys.executable, SCRIPT, "despacho"] + (["--hook"] if hook else [])
        p = subprocess.run(a, input=texto, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        return p

    def ctx(self, p):
        if not p.stdout.strip():
            return ""
        o = json.loads(p.stdout)
        h = o["hookSpecificOutput"]
        self.assertEqual(h["hookEventName"], "PreToolUse")
        return h["additionalContext"]

    def test_1_certo_fica_calado(self):
        self.assertEqual(self.desp("[sonnet:front] cartao").stdout.strip(), "")

    def test_2_explore_nada(self):
        p = self.desp("Explore the repo", st="Explore", model=None, prompt="x")
        self.assertEqual(p.stdout.strip(), "")

    def test_3_general_purpose_opus_nada(self):
        p = self.desp("Pesquisar precos", st="general-purpose", model="opus", prompt="x")
        self.assertEqual(p.stdout.strip(), "")

    def test_4_sem_model_sem_etiqueta(self):
        c = self.ctx(self.desp("cartao na lista", model=None))
        self.assertIn("sem model", c)
        self.assertIn("descricao sem [modelo:tipo]", c)
        self.assertIn('despacho "cartao na lista"', c)

    def test_5_modelo_diverge_e_opus_em_execucao(self):
        c = self.ctx(self.desp("[sonnet:front] cartao", st="orquestrador:orq-executor",
                               model="claude-opus-5-5"))
        self.assertIn("a descricao diz sonnet e o model e claude-opus-5-5", c)
        self.assertIn("opus em execucao: a ficha manda sonnet brief 3 pra front", c)

    def test_6_tipo_inexistente(self):
        c = self.ctx(self.desp("[sonnet:fronte] x", prompt="x"))
        self.assertIn('tipo "fronte" nao existe. Tipos: busca, leitura', c)

    def test_7_leitor_em_escrita(self):
        c = self.ctx(self.desp("[sonnet:edicao-logica] regra", st="orq-leitor"))
        self.assertIn("orq-leitor nao grava arquivo: tarefa de edicao-logica vai pra orq-executor", c)

    def test_8_sem_aceite(self):
        c = self.ctx(self.desp("[sonnet:front] cartao", prompt="OBJETIVO: x"))
        self.assertIn("brief sem ACEITE", c)

    def test_9_leitura_sem_aceite_ok(self):
        p = self.desp("[haiku:leitura] ler logs", st="orq-leitor", model="haiku", prompt="ler")
        self.assertEqual(p.stdout.strip(), "")

    def test_10_revisao_em_opus_ok(self):
        p = self.desp("[opus:revisao] diff", st="orq-revisor", model="opus", prompt="x")
        self.assertEqual(p.stdout.strip(), "")

    def test_11_etiqueta_em_general_purpose_ok(self):
        self.assertEqual(self.desp("[sonnet:front] x", st="general-purpose").stdout.strip(), "")

    def test_12_f_so_uma_vez_por_sessao(self):
        a = self.ctx(self.desp("[sonnet:front] cartao", model="claude-opus-5-5", sid="s1"))
        b = self.ctx(self.desp("[sonnet:front] cartao", model="claude-opus-5-5", sid="s1"))
        self.assertIn("opus em execucao", a)
        self.assertNotIn("opus em execucao", b)
        self.assertIn("a descricao diz sonnet", a)
        self.assertIn("a descricao diz sonnet", b)
        c = self.ctx(self.desp("[sonnet:front] cartao", model="claude-opus-5-5", sid="s2"))
        self.assertIn("opus em execucao", c)

    def test_13_variavel_desliga(self):
        p = self.desp("[sonnet:front] cartao", model="claude-opus-5-5",
                      env_extra={"ORQ_SEM_AVISO_DESPACHO": "1"})
        self.assertEqual(p.stdout.strip(), "")

    def test_14_entradas_ruins(self):
        for txt in ("", "{quebrado", "[]", json.dumps({"tool_name": "Bash", "tool_input": {}}),
                    json.dumps({"tool_name": "Agent", "tool_input": "x"})):
            p = self.bruto(txt)
            self.assertEqual(p.stdout.strip(), "", txt)

    def test_15_experimento_avisa_uma_vez(self):
        self.grava("front", "sonnet", "de_primeira", n=6, brief=3)
        self.assertTrue(self.ficha_json("front").get("experimento"))
        a = self.ctx(self.desp("[sonnet:front] x", sid="s9"))
        b = self.ctx(self.desp("[sonnet:front] x", sid="s9"))
        self.assertIn("experimento aberto em front: haiku brief 3", a)
        self.assertEqual(b, "")

    def test_avisos_torto_nao_derruba(self):
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        with io.open(os.path.join(os.path.dirname(self.registro), "despacho-avisos.json"),
                     "w", encoding="utf-8") as f:
            f.write("{torto")
        c = self.ctx(self.desp("[sonnet:front] cartao", model="claude-opus-5-5", sid="s1"))
        self.assertIn("opus em execucao", c)

    def test_nao_escreve_no_registro(self):
        self.desp("[sonnet:front] cartao", model="claude-opus-5-5", sid="s1")
        self.assertFalse(os.path.exists(self.registro))

    def test_sem_hook(self):
        self.assertIn("despacho ok", self.desp("[sonnet:front] cartao", hook=False).stdout)
        self.assertIn("nao e despacho da skill",
                      self.desp("Explore", st="Explore", model=None, hook=False).stdout)
        p = self.desp("cartao", model=None, prompt="x", hook=False)
        linhas = p.stdout.strip().splitlines()
        self.assertEqual(len(linhas), 3)
        self.assertTrue(linhas[0].startswith("sem model"))
        self.assertTrue(linhas[2].startswith("brief sem ACEITE"))

    def test_executor_sem_etiqueta_pede_aceite(self):
        # o papel orq-executor ja diz que a tarefa escreve, mesmo sem [modelo:tipo]
        c = self.ctx(self.desp("cartao", model=None, prompt="x"))
        for trecho in ("sem model", "descricao sem [modelo:tipo]", "brief sem ACEITE"):
            self.assertIn(trecho, c)
        self.assertNotIn("brief sem ACEITE", self.ctx(self.desp("cartao", model=None)))
        # leitor e revisor sem etiqueta nao recebem a cobranca de ACEITE
        self.assertNotIn("brief sem ACEITE", self.ctx(self.desp("ler logs", st="orq-leitor", prompt="x")))

    def test_acento_na_descricao(self):
        # o Claude Code manda UTF-8 cru (sem escape): a leitura nao pode depender do encoding do sistema
        nome = "cart" + chr(227) + "o novo"
        d = {"tool_name": "Agent", "tool_input": {"description": nome, "prompt": "ACEITE: x",
                                                  "subagent_type": "orq-executor"}}
        c = self.ctx(self.bruto(json.dumps(d, ensure_ascii=False)))
        self.assertIn('despacho "%s"' % nome, c)

    def test_nome_completo_do_modelo_bate_com_a_etiqueta(self):
        for modelo in ("claude-sonnet-5-5", "Sonnet", "sonnet[1m]"):
            self.assertEqual(self.desp("[sonnet:front] cartao", model=modelo).stdout.strip(), "", modelo)

    def test_papeis_que_nao_recebem_aviso(self):
        # debug que so le pode ir pro leitor; coordenacao e revisao em opus sao a rota normal
        casos = (("[haiku:debug] achar a causa", "orq-leitor", "haiku"),
                 ("[opus:coordenacao] frente 1", "orq-mestre", "opus"),
                 ("[fable:coordenacao] planta", "orq-engenheiro", "fable"),
                 ("[opus:revisao] diff de dinheiro", "orquestrador:orq-revisor", "opus"))
        for desc, papel, modelo in casos:
            self.assertEqual(self.desp(desc, st=papel, model=modelo).stdout.strip(), "", desc)

    def test_erro_interno_nao_vaza_no_hook(self):
        entrada = json.dumps({"tool_name": "Agent", "tool_input": {
            "description": "cartao", "prompt": "x", "subagent_type": "orq-executor"}})

        class Entrada(object):
            buffer = io.BytesIO(entrada.encode("utf-8"))

        def explode(*a, **k):
            raise RuntimeError("defeito de proposito")

        with mock.patch.object(operarios, "avaliar_despacho", explode), \
                mock.patch.object(operarios.sys, "stdin", Entrada()), \
                mock.patch.object(operarios.sys, "stdout", io.StringIO()) as saida:
            rc = operarios.cmd_despacho(mock.Mock(hook=True))
            self.assertEqual((rc, saida.getvalue()), (0, ""))
            Entrada.buffer = io.BytesIO(entrada.encode("utf-8"))
            with self.assertRaises(RuntimeError):   # fora do hook o erro aparece, pra dar pra consertar
                operarios.cmd_despacho(mock.Mock(hook=False))

    def test_saida_e_ascii(self):
        p = self.desp("cart" + chr(227) + "o", model=None)
        p.stdout.encode("ascii")


class TestDesign(Base):
    BOM = "ACEITE: print em desktop e celular ao lado da previa aprovada"

    def desp(self, desc, st="orq-designer", model="opus", prompt=None, sid=None):
        ti = {"description": desc, "prompt": self.BOM if prompt is None else prompt,
              "subagent_type": st}
        if model is not None:
            ti["model"] = model
        d = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "tool_input": ti}
        if sid:
            d["session_id"] = sid
        p = subprocess.run([sys.executable, SCRIPT, "despacho", "--hook"], input=json.dumps(d),
                           env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        if not p.stdout.strip():
            return ""
        return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_ficha_texto_tem_regra(self):
        p = self.run_op("ficha", "--tipo", "design")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("design -> opus brief 3", p.stdout)
        self.assertIn("\n  regra: design nao se fatia", p.stdout)

    def test_nota_da_ficha_tem_regra(self):
        self.grava("design", "opus", "de_primeira", n=1, brief=3)
        self.assertEqual(self.run_op("atualizar").returncode, 0)
        with io.open(self.ficha, encoding="utf-8") as f:
            nota = f.read()
        linha = [l for l in nota.splitlines() if l.startswith("| design |")]
        self.assertEqual(len(linha), 1, nota[:400])
        self.assertIn("regra: design nao se fatia", linha[0])
        self.assertNotIn("regra:", [l for l in nota.splitlines() if l.startswith("| front |")][0])

    def test_ficha_json_vazio(self):
        r = self.ficha_json("design")
        self.assertEqual((r["modelo"], r["brief"]), ("opus", 3))
        self.assertIsNone(r["experimento"])
        self.assertTrue(r["regra"].startswith("design nao se fatia"))

    def test_sonnet_de_primeira_nao_promove(self):
        self.grava("design", "sonnet", "de_primeira", n=8, brief=3)
        r = self.ficha_json("design")
        self.assertEqual(r["modelo"], "opus")
        self.assertIsNone(r["experimento"])

    def test_opus_de_primeira_nao_propoe_sonnet(self):
        self.grava("design", "opus", "de_primeira", n=8, brief=3)
        r = self.ficha_json("design")
        self.assertEqual(r["modelo"], "opus")
        self.assertIsNone(r["experimento"])

    def test_front_sem_regra(self):
        self.assertIsNone(self.ficha_json("front")["regra"])

    def test_aviso_h_sonnet(self):
        c = self.desp("[sonnet:design] inicio do site", model="sonnet")
        self.assertIn("design em sonnet", c)
        self.assertEqual(c.count("\n- "), 1)

    def test_aviso_h2_executor(self):
        c = self.desp("[opus:design] inicio", st="orq-executor")
        self.assertIn("orq-executor nao abre skill de design", c)
        self.assertEqual(c.count("\n- "), 1)

    def test_avisos_i_e_i2(self):
        c = self.desp("[opus:design] inicio", prompt="ACEITE: npm run build")
        self.assertIn("sem prova por print", c)
        self.assertIn("sem referencia visual", c)
        self.assertEqual(c.count("\n- "), 2)

    def test_bom_fica_calado(self):
        self.assertEqual(self.desp("[opus:design] inicio"), "")
        self.assertEqual(self.desp("[fable:design] inicio", model="fable"), "")

    def test_leitor_design_vai_pra_designer(self):
        c = self.desp("[opus:design] inicio", st="orq-leitor")
        self.assertIn("vai pra orq-designer", c)
        c2 = self.desp("[sonnet:front] cartao", st="orq-leitor", model="sonnet")
        self.assertIn("vai pra orq-executor", c2)

    def test_front_parece_design_uma_vez_por_sessao(self):
        d = "[sonnet:front] A4 pagina inicial estatica e responsiva"
        kw = dict(st="orq-executor", model="sonnet")
        self.assertIn("parece design", self.desp(d, sid="s1", **kw))
        self.assertNotIn("parece design", self.desp(d, sid="s1", **kw))
        self.assertIn("parece design", self.desp(d, sid="s2", **kw))

    def test_front_comum_sem_aviso_j(self):
        kw = dict(st="orq-executor", model="sonnet")
        c = self.desp("[sonnet:front] cartao na lista de clientes",
                      prompt="OBJETIVO: ligar o campo saldo ACEITE: npm test", **kw)
        self.assertNotIn("parece design", c)
        c = self.desp("[sonnet:front] ajuste",
                      prompt="ACEITE: x. Texto: a homologacao do heroi", **kw)
        self.assertNotIn("parece design", c)
        # tela comum que so cita responsivo ou bonito nao e design
        for texto in ("ACEITE: teste. Tela responsiva ja pronta", "ACEITE: x. O dashboard bonito ja existe",
                      "ACEITE: x. O responsavel pelo home office"):
            self.assertNotIn("parece design", self.desp("[sonnet:front] ligar campo", prompt=texto, **kw), texto)

    def test_front_parece_design_termos(self):
        kw = dict(st="orq-executor", model="sonnet")
        termos = ("landing page do produto", "tela inicial do app", "pagina de vendas", "novo layout do painel",
                  "nova tela de cadastro", "redesenhar o cabecalho", "acabamento visual")
        for i, t in enumerate(termos):
            c = self.desp("[sonnet:front] " + t, prompt="ACEITE: x", sid="t%d" % i, **kw)
            self.assertIn("parece design", c, t)

    def test_poucos_registros_no_modelo_menor_nao_abrem_experimento(self):
        # sem a guarda, 2 registros de design em sonnet (sem prova com brief 3) viravam experimento
        self.grava("design", "sonnet", "de_primeira", n=2, brief=2)
        r = self.ficha_json("design")
        self.assertEqual(r["modelo"], "opus")
        self.assertIsNone(r["experimento"])

    def test_opus_reprovado_cai_no_chefe(self):
        self.grava("design", "opus", "falhou", n=3, brief=3)
        r = self.ficha_json("design")
        self.assertEqual(r["modelo"], "chefe")
        self.assertIsNone(r["experimento"])


class TestReprovar(Base):
    def linhas(self):
        return self.le(self.registro).splitlines(True)

    def test_de_primeira_vira_corrigido(self):
        self.grava("front", "sonnet", "de_primeira", id="aaaa1111", tarefa="t1", licao="L")
        p = self.run_op("reprovar", "--id", "aaaa1111", "--erro", "visual: dono reprovou o inicio")
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(self.linhas()[0])
        self.assertEqual((d["resultado"], d["rodadas"], d["classes"], d["reprovado"]),
                         ("corrigido", 1, ["visual"], True))
        self.assertEqual(d["erros"], ["dono reprovou o inicio"])
        self.assertEqual(d["licao"], "L")
        self.assertIn("reprovado: aaaa1111 front sonnet de_primeira -> corrigido (rodadas 1)", p.stdout)

    def test_agente_pega_o_mais_recente(self):
        self.grava("front", "sonnet", "de_primeira", id="aaaa1111", tarefa="mesma")
        self.grava("front", "sonnet", "de_primeira", id="bbbb2222", tarefa="mesma")
        antes = self.linhas()
        p = self.run_op("reprovar", "--agente", "mesma", "--erro", "visual: x")
        self.assertEqual(p.returncode, 0, p.stderr)
        depois = self.linhas()
        self.assertEqual(depois[0], antes[0])
        self.assertEqual(json.loads(depois[1])["resultado"], "corrigido")

    def test_falhou_e_escalado_mantem_o_resultado(self):
        for i, res in enumerate(("falhou", "escalado")):
            rid = "bbbb000%d" % i
            self.grava("front", "sonnet", res, id=rid)
            p = self.run_op("reprovar", "--id", rid, "--erro", "visual: x")
            self.assertEqual(p.returncode, 0, p.stderr)
            d = [json.loads(l) for l in self.linhas() if rid in l][0]
            self.assertEqual((d["resultado"], d["classes"], d["reprovado"]), (res, ["visual"], True))
            self.assertGreaterEqual(d["rodadas"], 1)

    def test_corrigido_acumula(self):
        self.grava("front", "sonnet", "corrigido", id="aaaa1111", erros=["a"], classes=["borda"])
        p = self.run_op("reprovar", "--id", "aaaa1111", "--erro", "visual: b")
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(self.linhas()[0])
        self.assertEqual((d["resultado"], d["rodadas"], d["erros"], d["classes"]),
                         ("corrigido", 2, ["a", "b"], ["borda", "visual"]))

    def test_duas_vezes_e_sem_campo_rodadas(self):
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        with io.open(self.registro, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps({"id": "aaaa1111", "tipo": "front", "modelo": "sonnet",
                                "resultado": "de_primeira"}) + "\n")
        for t in ("visual: a", "visual: b"):
            p = self.run_op("reprovar", "--id", "aaaa1111", "--erro", t)
            self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(self.linhas()[0])
        self.assertEqual((d["rodadas"], d["classes"], len(d["erros"])), (2, ["visual"], 2))

    def test_recusas_deixam_arquivo_igual(self):
        self.grava("front", "sonnet", "anulado", id="anul1111", tarefa="t")
        self.grava("front", "sonnet", "de_primeira", id="aaaa1111", tarefa="t2")
        antes = self.le(self.registro)
        casos = [
            ("--id", "anul1111", "--erro", "visual: x"),
            ("--id", "aaaa1111", "--erro", "ficou feio"),
            ("--id", "naoexiste", "--erro", "visual: x"),
            ("--erro", "visual: x"),
            ("--id", "aaaa1111", "--agente", "t2", "--erro", "visual: x"),
            ("--id", "aaaa1111"),
        ]
        for c in casos:
            p = self.run_op("reprovar", *c)
            self.assertEqual(p.returncode, 13, (c, p.stdout))
            self.assertNotIn("Traceback", p.stderr)
            self.assertEqual(self.le(self.registro), antes, c)
        p = self.run_op("reprovar", "--id", "aaaa1111", "--erro", "ficou feio")
        self.assertIn("Classes:", p.stderr)
        self.assertIn("Nada foi alterado.", p.stderr)

    def test_bom_crlf_fim_sem_quebra(self):
        def lin(i):
            return json.dumps({"id": i, "tipo": "front", "modelo": "sonnet",
                               "resultado": "de_primeira", "rodadas": 0}).encode("utf-8")
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        with io.open(self.registro, "wb") as f:
            f.write(b"\xef\xbb\xbf" + lin("a") + b"\r\n" + lin("b") + b"\r\n" + lin("c"))
        p = self.run_op("reprovar", "--id", "b", "--erro", "visual: x")
        self.assertEqual(p.returncode, 0, p.stderr)
        with io.open(self.registro, "rb") as f:
            depois = f.read()
        partes = depois.split(b"\r\n")
        self.assertEqual(len(partes), 3)
        self.assertEqual(partes[0], lin("a"))
        self.assertEqual(partes[2], lin("c"))
        self.assertTrue(json.loads(partes[1])["reprovado"])
        self.assertFalse(depois.endswith(b"\n"))

    def test_byte_invalido(self):
        os.makedirs(os.path.dirname(self.registro), exist_ok=True)
        bruto = b'{"id": "aaaa1111"}\n\xff\xfe lixo\n'
        with io.open(self.registro, "wb") as f:
            f.write(bruto)
        p = self.run_op("reprovar", "--id", "aaaa1111", "--erro", "visual: x")
        self.assertEqual(p.returncode, 13, p.stdout)
        self.assertIn("Nada foi alterado", p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        with io.open(self.registro, "rb") as f:
            self.assertEqual(f.read(), bruto)

    def test_copia_antes_de_reprovar(self):
        self.grava("front", "sonnet", "de_primeira", id="aaaa1111")
        antes = self.le(self.registro)
        p = self.run_op("reprovar", "--id", "aaaa1111", "--erro", "visual: x")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.le(self.registro + ".antes-de-reprovar"), antes)

    def test_ficha_deixa_de_contar_de_primeira(self):
        for i in range(4):
            self.grava("front", "sonnet", "de_primeira", brief=3, id="id00000%d" % i)
        antes = json.dumps(self.ficha_json("front"), sort_keys=True)
        for i in range(3):
            p = self.run_op("reprovar", "--id", "id00000%d" % i, "--erro", "visual: feio")
            self.assertEqual(p.returncode, 0, p.stderr)
        depois = json.dumps(self.ficha_json("front"), sort_keys=True)
        self.assertNotEqual(antes, depois)
        self.assertNotIn("4/4", depois)


if __name__ == "__main__":
    unittest.main()
