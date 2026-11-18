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
        p = self.reg("busca", "haiku", "falhou", erros=["vazou token " + segredo],
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
        self.reg("teste", "sonnet", "corrigido", rodadas=1, erros=["a", "a"])
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
        self.assertEqual(p.returncode, 0, p.stderr)
        d = json.loads(p.stdout)
        self.assertEqual(d["classes"], ["outro"])
        self.assertEqual(d["erros"], ["texto sem classe"])

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


if __name__ == "__main__":
    unittest.main()
