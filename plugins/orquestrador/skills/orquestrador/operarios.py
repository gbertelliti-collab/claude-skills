#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""operarios.py - motor da skill orquestrador.

Registra como cada operario (haiku/sonnet/opus) se saiu em cada tarefa e devolve
uma ficha com a rota recomendada aprendida do historico.

Comandos: status, registrar, ficha, conferir, resumo, atualizar.
Variaveis de ambiente: ORQ_REGISTRO (registro; padrao ~/.claude/orquestrador/registro.jsonl),
ORQ_FICHA (arquivo .md onde `atualizar` grava a ficha; sem ela `atualizar` so avisa e sai 0),
ORQ_PROJECTS (transcripts; padrao ~/.claude/projects).
CLAUDE_CODE_SESSION_ID (do Claude Code) escopa conferir/registrar/resumo na sessao atual.
"""
import argparse
import hashlib
import io
import json
import os
import re
import statistics
import sys
import tempfile
import time
from datetime import datetime, timedelta

# ----------------------------------------------------------------------------
# Constantes ajustaveis
# ----------------------------------------------------------------------------
TIPOS = ["busca", "leitura", "pesquisa-web", "edicao-mecanica", "edicao-logica",
         "teste", "dados-sql", "front", "debug", "texto", "revisao", "coordenacao", "outro"]
MODELOS = ["haiku", "sonnet", "opus", "fable", "chefe"]
RESULTADOS = ["de_primeira", "corrigido", "escalado", "falhou", "anulado"]
CLASSES_ERRO = {
    "escopo": ("mexeu fora ou esqueceu um lugar que usa",
               "liste TODOS os lugares que usam o que muda (grep colado)"),
    "contrato": ("assinatura, tipo, nome de campo, formato",
                 "cole a assinatura, o tipo e o nome de campo exatos dos dois lados"),
    "borda": ("vazio, nulo, limite, data",
              "tabela de casos com vazio, nulo, zero, limite e data torta"),
    "estado": ("ordem dos eventos, ciclo de vida, cache",
               "a ordem dos eventos e o que acontece ao repetir, cancelar, recarregar"),
    "desempenho": ("laco, por quadro, por linha",
                   "o que roda em laco ou por quadro e o teto aceito"),
    "teste": ("sem teste ou teste que nao prova",
              "o teste que tem que existir e o que ele tem que derrubar"),
    "alegacao": ("disse feito sem prova",
                 "exija a saida real colada de cada comando do ACEITE"),
    "leitura": ("leu errado ou inventou",
                "exija trecho copiado com arquivo:linha em cada afirmacao"),
    "visual": ("layout, foco, corte",
               "medida, estado de foco e o que nao pode cortar ou sobrepor"),
    "seguranca": ("acesso, vazamento, segredo",
                  "quem pode chamar, o que nao pode vazar, falha fechada"),
    "outro": ("nao coube", ""),
}
_NOMES_CLASSE = list(CLASSES_ERRO)
EFFORTS = ["low", "medium", "high", "xhigh", "max"]
ESCADA = ["haiku", "sonnet", "opus"]   # roteamento; "chefe" e so o destino final
ALIASES = ["haiku", "sonnet", "opus", "fable"]

PADRAO = {
    "busca": ("haiku", 2),
    "leitura": ("haiku", 2),
    "pesquisa-web": ("haiku", 2),
    "edicao-mecanica": ("sonnet", 3),
    "edicao-logica": ("sonnet", 3),
    "teste": ("sonnet", 3),
    "dados-sql": ("sonnet", 3),
    "front": ("sonnet", 3),
    "debug": ("sonnet", 3),
    "texto": ("sonnet", 3),
    "revisao": ("sonnet", 2),
    "coordenacao": ("opus", 3),
    "outro": ("sonnet", 3),
}
EXPERIMENTAR_BRIEF_MENOR = False
JANELA = 20             # ultimos N registros por (tipo, modelo)
MIN_N = 4               # minimo de registros num balde pra confiar
TAXA_OK_MIN = 0.6       # abaixo disso o balde "nao da"
TAXA_1A_MIN = 0.5       # abaixo disso o balde "precisa ajuda"
TAXA_1A_PROMOVER = 0.8  # a partir disso promove pro modelo mais barato
FALHAS_SEGUIDAS = 3     # balde duro: ultimas N todas escalado/falhou
RETESTE_DIAS = 30
BRIEF_MENOR_N = 6
BRIEF_MENOR_TAXA = 0.9
MAX_AVISOS = 3
JANELA_GERAL = 60
TIPOS_EXPERIMENTO = {"busca", "leitura", "pesquisa-web", "edicao-mecanica", "teste"}
TIPOS_EXP_FORTE = {"front", "edicao-logica", "texto", "outro"}
TIPOS_SEM_BARATO = {"revisao", "debug", "dados-sql", "coordenacao"}
EXP_FORTE_N = 6
EXP_FORTE_TAXA = 0.75
EXP_META = 4
TOKENS_V = 2            # versao da contagem de tokens_saida (1 = somava linha, 2 = por resposta)
MAX_FRENTE = 40
MAX_ERRO = 160
MAX_TAREFA = 160
MAX_LICAO = 200
MAX_BRIEF_EXEMPLO = 6000

MARC_INI = "<!-- auto:inicio -->"
MARC_FIM = "<!-- auto:fim -->"


# ----------------------------------------------------------------------------
# Caminhos
# ----------------------------------------------------------------------------
def p_registro():
    return os.environ.get("ORQ_REGISTRO") or os.path.join(
        os.path.expanduser("~"), ".claude", "orquestrador", "registro.jsonl")


def p_ficha():
    """Arquivo da ficha gravada por `atualizar`. None = ORQ_FICHA nao definida (nao grava)."""
    return os.environ.get("ORQ_FICHA") or None


def p_projects():
    return os.environ.get("ORQ_PROJECTS") or os.path.join(
        os.path.expanduser("~"), ".claude", "projects")


def p_exemplos():
    return os.path.join(os.path.dirname(os.path.abspath(p_registro())), "exemplos")


def p_exemplo(tipo, modelo):
    return os.path.join(p_exemplos(), "%s--%s.md" % (tipo, modelo))


def sessao_atual():
    return os.environ.get("CLAUDE_CODE_SESSION_ID") or None


def _long(p):
    """Prefixo \\\\?\\ no Windows: transcripts passam de 260 chars."""
    p = os.path.abspath(p)
    if os.name == "nt" and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + p
    return p


# ----------------------------------------------------------------------------
# Redacao e limpeza
# ----------------------------------------------------------------------------
_FALLBACK = [
    ("chave", re.compile(r"(?:sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{16,}|gho_[A-Za-z0-9]{16,}"
                         r"|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16})")),
    ("bearer", re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-~+/=]{6,}")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("cpf", re.compile(r"(?<!\d)\d{11}(?!\d)")),
]


def _fallback_redigir(texto):
    if not texto:
        return texto, []
    achados = []
    for classe, rx in _FALLBACK:
        def _rep(m, c=classe):
            achados.append(c)
            return "[REDIGIDO:%s]" % c
        texto = rx.sub(_rep, texto)
    return texto, achados


_REDATOR, _REDACAO_MODO = _fallback_redigir, "interno"


def redigir(texto):
    if not texto:
        return texto, []
    try:
        t, cls = _REDATOR(texto)
    except Exception:
        t, cls = _fallback_redigir(texto)
    return t, list(cls)


def _limpar(s):
    """Uma linha so, sem marcadores de comentario HTML nem pipe."""
    s = re.sub(r"\s+", " ", str(s if s is not None else "")).strip()
    for _ in range(6):
        antes = s
        s = s.replace("-->", "- ->").replace("<!--", "<!- -").replace("|", "/")
        if s == antes:
            break
    return s


# ----------------------------------------------------------------------------
# Registro
# ----------------------------------------------------------------------------
def _norm_reg(d):
    if not isinstance(d, dict):
        return None
    tipo, modelo, res = d.get("tipo"), d.get("modelo"), d.get("resultado")
    if tipo not in TIPOS or modelo not in MODELOS or res not in RESULTADOS:
        return None
    r = dict(d)
    er = d.get("erros")
    if isinstance(er, str):
        er = [er]
    if not isinstance(er, list):
        er = []
    r["erros"] = [_limpar(e if isinstance(e, str) else str(e)) for e in er]
    cl = d.get("classes")
    if isinstance(cl, list) and len(cl) == len(r["erros"]):
        r["classes"] = [c if (isinstance(c, str) and c in _NOMES_CLASSE) else "outro" for c in cl]
    else:
        r["classes"] = ["outro"] * len(r["erros"])
    r["licao"] = _limpar(d["licao"] if isinstance(d.get("licao"), str) else
                         ("" if d.get("licao") is None else str(d.get("licao"))))
    b = d.get("brief")
    if isinstance(b, bool) or not isinstance(b, int) or b < 1 or b > 3:
        b = PADRAO[tipo][1]
    r["brief"] = b
    ro = d.get("rodadas")
    r["rodadas"] = ro if isinstance(ro, int) and not isinstance(ro, bool) else 0
    if not isinstance(r.get("ts"), str):
        r["ts"] = ""
    return r


def ler_registro_ex():
    p = p_registro()
    regs, ign = [], 0
    if not os.path.exists(p):
        return regs, ign
    try:
        with io.open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            linhas = f.read().splitlines()
    except OSError:
        return regs, ign
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        try:
            r = _norm_reg(json.loads(linha))
        except Exception:
            r = None
        if r is None:
            ign += 1
        else:
            regs.append(r)
    return regs, ign


def ler_registro():
    return ler_registro_ex()[0]


def _garantir_pasta(path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)


def cmd_status(args):
    reg = p_registro()
    try:
        _garantir_pasta(reg)
    except OSError as e:
        print("erro: nao consegui criar a pasta do registro: %s" % e, file=sys.stderr)
        return 13
    ficha = p_ficha()
    regs, ign = ler_registro_ex()
    out = {
        "canario": "ok",
        "registro": reg,
        "n_registros": len(regs),
        "linhas_ignoradas": ign,
        "ficha": ficha,
        "ficha_existe": bool(ficha) and os.path.exists(ficha),
        "redacao": _REDACAO_MODO,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------------
# Agentes (transcripts)
# ----------------------------------------------------------------------------
def _achar_metas(raiz, limite_ts, sessao=None):
    """Varre <raiz>/*/<sessao>/subagents/agent-*.meta.json com mtime >= limite."""
    achados = []
    try:
        projetos = list(os.scandir(_long(raiz)))
    except OSError:
        return achados
    for proj in projetos:
        try:
            if not proj.is_dir():
                continue
            sessoes = list(os.scandir(proj.path))
        except OSError:
            continue
        for sess in sessoes:
            try:
                if not sess.is_dir():
                    continue
                if sessao and sess.name != sessao:
                    continue
                sub = os.path.join(sess.path, "subagents")
                if not os.path.isdir(sub):
                    continue
                for f in os.scandir(sub):
                    if f.name.startswith("agent-") and f.name.endswith(".meta.json"):
                        try:
                            mt = f.stat().st_mtime
                        except OSError:
                            continue
                        if mt >= limite_ts:
                            achados.append(f.path)
            except OSError:
                continue
    return achados


def _ler_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _int0(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def analisar_agente(meta_path):
    try:
        meta = _ler_json(meta_path)
    except Exception:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    desc = meta.get("description")
    desc = desc if isinstance(desc, str) else ""
    pedido = meta.get("model") or None
    if pedido is not None and not isinstance(pedido, str):
        pedido = str(pedido)
    jsonl = meta_path[:-len(".meta.json")] + ".jsonl"
    reais = {}
    # varias linhas "assistant" por resposta (1 por bloco, mesmo message.id e mesma usage):
    # agrupa por id e fica com a usage de maior output_tokens (empate: a primeira)
    resp = {}
    try:
        with io.open(jsonl, "r", encoding="utf-8", errors="replace") as f:
            for n, linha in enumerate(f):
                linha = linha.strip()
                if not linha or '"assistant"' not in linha:
                    continue
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if not isinstance(d, dict) or d.get("type") != "assistant":
                    continue
                msg = d.get("message")
                if not isinstance(msg, dict):
                    msg = {}
                mod = msg.get("model")
                mod = mod if isinstance(mod, str) else None
                u = msg.get("usage")
                if not isinstance(u, dict):
                    u = {}
                # campo torto zera so ele, nao a resposta inteira
                o = _int0(u.get("output_tokens"))
                c = (_int0(u.get("input_tokens")) + _int0(u.get("cache_read_input_tokens"))
                     + _int0(u.get("cache_creation_input_tokens")))
                mid = msg.get("id")
                chave = mid if isinstance(mid, str) and mid else "__linha_%d" % n
                atual = resp.get(chave)
                if atual is None:
                    resp[chave] = {"o": o, "c": c, "mod": mod}
                else:
                    if o > atual["o"]:
                        atual["o"], atual["c"] = o, c
                        if mod:
                            atual["mod"] = mod
                    if not atual["mod"] and mod:
                        atual["mod"] = mod
    except OSError:
        pass
    saida = 0
    ctx = 0
    for v in resp.values():
        saida += v["o"]
        ctx = max(ctx, v["c"])
        if v["mod"] and v["mod"] != "<synthetic>":
            reais[v["mod"]] = reais.get(v["mod"], 0) + 1
    tipo = None
    m = re.match(r"^\s*\[[^:\]]+:\s*([^\]]+?)\s*\]", desc)
    if m:
        tipo = m.group(1)
    if not reais:
        status = "SEM-DADO"
    elif pedido is None or pedido.lower() == "inherit":
        status = "herdou"
    elif pedido.lower() in ALIASES:
        status = "DIVERGIU" if any(pedido.lower() not in mod.lower() for mod in reais) else "ok"
    else:
        status = "ok" if all(mod == pedido for mod in reais) else "DIVERGIU"
    sd = meta.get("spawnDepth")
    prof = sd if isinstance(sd, int) and not isinstance(sd, bool) and sd >= 1 else 1
    if prof >= 3:
        status = "ANDAR-3"
    elif prof >= 2 and pedido is None:
        status = "SEM-MODELO"
    pai = meta.get("parentAgentId")
    pai = pai if isinstance(pai, str) and pai else None
    return {
        "agente": os.path.basename(meta_path)[:-len(".meta.json")],
        "profundidade": prof,
        "pai": pai,
        "descricao": desc,
        "tipo": tipo,
        "pedido": pedido,
        "reais": reais,
        "tokens_saida": saida,
        "respostas": len(resp),
        "contexto_max": ctx,
        "status": status,
        "_jsonl": jsonl,
    }


def _alias_real(reais):
    if not reais:
        return None
    top = sorted(reais.items(), key=lambda kv: -kv[1])[0][0].lower()
    for a in ALIASES:
        if a in top:
            return a
    return None


def _brief_do_agente(jsonl):
    try:
        with io.open(jsonl, "r", encoding="utf-8", errors="replace") as f:
            for i, linha in enumerate(f):
                if i >= 20:
                    break
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("type") == "user":
                    c = (d.get("message") or {}).get("content")
                    if isinstance(c, str):
                        return c
                    if isinstance(c, list):
                        return "\n".join(b.get("text", "") for b in c
                                         if isinstance(b, dict) and b.get("type") == "text"
                                         and isinstance(b.get("text"), str))
    except OSError:
        pass
    return ""


def _parse_janela(s):
    m = re.match(r"^(\d+)\s*([hd])$", (s or "").strip().lower())
    if not m:
        raise ValueError("--desde invalido: use Nh ou Nd (ex.: 12h, 2d)")
    n = int(m.group(1))
    return n * 3600 if m.group(2) == "h" else n * 86400


def _parse_ts(s):
    try:
        d = datetime.fromisoformat(s)
    except Exception:
        return None
    if d.tzinfo is None:
        d = d.astimezone()
    return d


def cmd_conferir(args):
    try:
        seg = _parse_janela(args.desde)
    except ValueError as e:
        print("erro: %s" % e, file=sys.stderr)
        return 13
    sessao = args.sessao or (None if args.todas else sessao_atual())
    metas = _achar_metas(p_projects(), time.time() - seg, sessao)
    ags = [analisar_agente(m) for m in metas]
    for a in ags:
        a.pop("_jsonl", None)
    if not ags:
        if args.json:
            print("[]")
        else:
            print("nenhum subagente na janela de %s%s" % (
                args.desde, (" (sessao %s)" % sessao) if sessao else ""))
        return 10
    ags.sort(key=lambda a: a["agente"])
    cont = {"ok": 0, "DIVERGIU": 0, "herdou": 0, "SEM-DADO": 0, "ANDAR-3": 0, "SEM-MODELO": 0}
    for a in ags:
        cont[a["status"]] += 1
    # ordem em arvore: cada raiz seguida dos filhos (recursivo)
    ids = set(a["agente"] for a in ags)
    filhos = {}
    raizes = []
    for a in ags:
        pai = a.get("pai")
        pid = None
        if pai:
            pid = pai if pai.startswith("agent-") else "agent-" + pai
        if pid and pid in ids and pid != a["agente"]:
            filhos.setdefault(pid, []).append(a)
        else:
            raizes.append(a)
    arvore = []
    vistos = set()

    def _desce(a, nivel):
        if a["agente"] in vistos:
            return
        vistos.add(a["agente"])
        arvore.append((a, nivel))
        for f in filhos.get(a["agente"], []):
            _desce(f, nivel + 1)

    for a in raizes:
        _desce(a, 1)
    for a in ags:   # ciclo improvavel: nao perder agente
        _desce(a, 1)
    ags = [a for a, _ in arvore]
    if args.json:
        print(json.dumps(ags, ensure_ascii=False, indent=2))
    else:
        print("%-10s %-8s %-14s %-26s %8s %8s %2s  %s" % (
            "status", "pedido", "tipo", "reais", "saida", "ctx_max", "nv", "descricao"))
        for a, nivel in arvore:
            reais = ",".join("%s x%d" % (k, v) for k, v in a["reais"].items()) or "-"
            pref = "" if nivel == 1 else "  " * (nivel - 1) + "└ "
            print("%-10s %-8s %-14s %-26s %8d %8d %2d  %s" % (
                a["status"], a["pedido"] or "-", (a["tipo"] or "-")[:14], reais[:26],
                a["tokens_saida"], a["contexto_max"], a["profundidade"],
                pref + a["descricao"][:60]))
        linha = "%d agentes: %d ok, %d DIVERGIU, %d herdou, %d sem dado" % (
            len(ags), cont["ok"], cont["DIVERGIU"], cont["herdou"], cont["SEM-DADO"])
        F = len([a for a in ags if a["profundidade"] == 2])
        B = len([a for a in ags if a["profundidade"] >= 3])
        if F > 0:
            linha += ", %d netos" % F
        if B > 0:
            linha += ", %d bisnetos (PROIBIDO)" % B
        if cont["SEM-MODELO"] > 0:
            linha += ", %d sem modelo" % cont["SEM-MODELO"]
        print(linha)
    return 3 if (cont["DIVERGIU"] or cont["ANDAR-3"] or cont["SEM-MODELO"]) else 0


# ----------------------------------------------------------------------------
# Registrar
# ----------------------------------------------------------------------------
def _trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n]


def _achar_agente(texto):
    """Devolve (info, erro_msg)."""
    sessao = sessao_atual()
    metas = _achar_metas(p_projects(), 0, sessao)
    alvo = _limpar(texto).lower()
    cands = []
    for m in metas:
        info = analisar_agente(m)
        d = _limpar(info["descricao"]).lower()
        if d == alvo or d.startswith(alvo):
            cands.append(info)
    iguais = [c for c in cands if _limpar(c["descricao"]).lower() == alvo]
    if iguais:
        cands = iguais
    if len(cands) == 1:
        return cands[0], None
    if not cands:
        return None, "nenhum agente com descricao igual ou iniciada por %r" % texto
    return None, "mais de um agente casa com %r: %s" % (
        texto, " | ".join(_limpar(c["descricao"])[:60] for c in cands))


TRAVA_S = 10.0       # prazo pra pegar a trava do registro
TRAVA_PASSO_S = 0.05


def _pegar_trava(fd):
    """Tenta travar o byte 0 de fd sem bloquear. True se pegou."""
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _soltar_trava(fd):
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def _com_trava(caminho_trava, func):
    """Roda func() com a trava de arquivo `caminho_trava` (criada se faltar, nunca apagada).
    Sem trava em TRAVA_S segundos: avisa em stderr e roda func() assim mesmo."""
    fd = os.open(caminho_trava, os.O_RDWR | os.O_CREAT)
    pegou = False
    try:
        fim = time.time() + TRAVA_S
        while True:
            pegou = _pegar_trava(fd)
            if pegou or time.time() >= fim:
                break
            time.sleep(TRAVA_PASSO_S)
        if not pegou:
            print("aviso: registro sem trava apos 10 s; gravando assim mesmo", file=sys.stderr)
        return func()
    finally:
        if pegou:
            _soltar_trava(fd)
        os.close(fd)


def cmd_registrar(args):
    if args.brief < 1 or args.brief > 3:
        print("erro: --brief deve ser 1, 2 ou 3", file=sys.stderr)
        return 13
    if args.rodadas < 0:
        print("erro: --rodadas nao pode ser negativo", file=sys.stderr)
        return 13
    if args.resultado == "de_primeira" and args.rodadas != 0:
        print("erro: de_primeira exige --rodadas 0", file=sys.stderr)
        return 13
    if args.resultado == "corrigido" and args.rodadas < 1:
        print("erro: corrigido exige --rodadas >= 1", file=sys.stderr)
        return 13

    tipo, modelo = args.tipo, args.modelo
    info = None
    pedido = None
    if args.agente:
        info, msg = _achar_agente(args.agente)
        if info is None:
            print("erro: %s" % msg, file=sys.stderr)
            return 13
        if not tipo:
            tipo = info["tipo"]
        real = _alias_real(info["reais"])
        if real:
            if modelo and modelo != real:
                pedido = modelo
                print("AVISO: pedido %s, rodou %s" % (modelo, real), file=sys.stderr)
            modelo = real
    if tipo not in TIPOS:
        print("erro: nao consegui determinar o tipo (use --tipo ou a tag [modelo:tipo] na descricao)",
              file=sys.stderr)
        return 13
    if modelo not in MODELOS:
        print("erro: nao consegui determinar o modelo (use --modelo)", file=sys.stderr)
        return 13

    classes = []

    def limpa(txt, n):
        if txt is None:
            return None
        t, cls = redigir(txt)
        classes.extend(cls)
        return _trunc(_limpar(t), n)

    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    rec = {
        "tipo": tipo,
        "modelo": modelo,
        "resultado": args.resultado,
        "rodadas": args.rodadas,
        "brief": args.brief,
    }
    if args.effort:
        rec["effort"] = args.effort
    erros, classes_e = [], []
    for e in (args.erro or []):
        classe, det = "outro", e
        mm = re.match(r"^\s*([A-Za-z]+)\s*:(.*)$", e, re.S)
        if mm and mm.group(1).lower() in _NOMES_CLASSE:
            classe = mm.group(1).lower()
            det = mm.group(2).strip() or e
        erros.append(limpa(det, MAX_ERRO))
        classes_e.append(classe)
    if erros:
        rec["erros"] = erros
        rec["classes"] = classes_e
    if args.frente:
        fr = limpa(args.frente, MAX_FRENTE)
        if fr:
            rec["frente"] = fr
    if args.licao:
        rec["licao"] = limpa(args.licao, MAX_LICAO)
    if args.projeto:
        rec["projeto"] = limpa(args.projeto, MAX_TAREFA)
    tarefa = args.tarefa or (info["descricao"] if info else None)
    if tarefa:
        rec["tarefa"] = limpa(tarefa, MAX_TAREFA)
    if args.experimento:
        rec["experimento"] = True
    if args.tokens is not None:
        rec["tokens"] = args.tokens
    if sessao_atual():
        rec["sessao"] = sessao_atual()
    if info:
        rec["agente"] = info["agente"]
        rec["tokens_saida"] = info["tokens_saida"]
        rec["respostas"] = info["respostas"]
        rec["tokens_v"] = TOKENS_V
        rec["contexto_max"] = info["contexto_max"]
        rec["profundidade"] = info["profundidade"]
        if info.get("pai"):
            pai = info["pai"]
            nome = pai if pai.startswith("agent-") else "agent-" + pai
            mp = os.path.join(os.path.dirname(info["_jsonl"]), nome + ".meta.json")
            try:
                dp = _ler_json(mp)
                dd = dp.get("description") if isinstance(dp, dict) else None
                if isinstance(dd, str) and dd:
                    rec["mestre"] = limpa(dd, MAX_TAREFA)
            except Exception:
                pass
    if pedido:
        rec["pedido"] = pedido
    if classes:
        rec["redigido"] = sorted(set(classes))
    base = "%s|%s|%d|%d" % (json.dumps(rec, ensure_ascii=False, sort_keys=True), ts,
                            time.time_ns(), os.getpid())
    ordenado = {"ts": ts, "id": hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]}
    ordenado.update(rec)
    linha = json.dumps(ordenado, ensure_ascii=False)
    reg = p_registro()
    try:
        _garantir_pasta(reg)
        def _grava():
            with io.open(reg, "a", encoding="utf-8", newline="") as f:
                f.write(linha + "\n")
        _com_trava(reg + ".trava", _grava)
    except OSError as e:
        print("erro: nao consegui gravar o registro: %s" % e, file=sys.stderr)
        return 13

    if info and args.resultado == "de_primeira":
        try:
            brief_txt = _brief_do_agente(info["_jsonl"])
            if brief_txt:
                t, _ = redigir(brief_txt)
                t = _trunc(t, MAX_BRIEF_EXEMPLO)
                cab = "# %s | %s | %s" % (ts[:10], rec.get("projeto", "-"), rec.get("tarefa", "-"))
                os.makedirs(p_exemplos(), exist_ok=True)
                with io.open(p_exemplo(tipo, modelo), "w", encoding="utf-8", newline="") as f:
                    f.write(cab + "\n\n" + t + "\n")
        except OSError as e:
            print("AVISO: nao consegui salvar o exemplo: %s" % e, file=sys.stderr)
    print(linha)
    return 0


# ----------------------------------------------------------------------------
# Rota (evidencia por nivel de brief)
# ----------------------------------------------------------------------------
def _norm_erro(e):
    e = (e or "").lower().strip()
    e = re.sub(r"\s+", " ", e)
    e = re.sub(r"[\s\.\,\;\:\!\?]+$", "", e)
    return e


def _pares(regs, tipo, m):
    return [r for r in regs if r["tipo"] == tipo and r["modelo"] == m
            and r["resultado"] != "anulado"][-JANELA:]


def _balde(regs, tipo, m, L):
    return [r for r in _pares(regs, tipo, m) if r["brief"] == L]


def _tok_saida(r):
    """tokens_saida so vale se contado por resposta (tokens_v == TOKENS_V)."""
    t = r.get("tokens_saida")
    tv = r.get("tokens_v")
    if isinstance(tv, bool) or tv != TOKENS_V:
        return None
    return t if isinstance(t, int) and not isinstance(t, bool) else None


def _bstats(lista):
    n = len(lista)
    c = {k: 0 for k in RESULTADOS}
    toks = []
    for r in lista:
        c[r["resultado"]] += 1
        t = _tok_saida(r)
        if t is not None:
            toks.append(t)
    return {
        "tok_med": statistics.median(toks) if toks else None,
        "n": n,
        "de_primeira": c["de_primeira"],
        "corrigido": c["corrigido"],
        "escalado": c["escalado"],
        "falhou": c["falhou"],
        "p1": round(c["de_primeira"] / n, 3) if n else 0.0,
        "pok": round((c["de_primeira"] + c["corrigido"]) / n, 3) if n else 0.0,
    }


def _duro(b):
    return len(b) >= FALHAS_SEGUIDAS and all(
        r["resultado"] in ("escalado", "falhou") for r in b[-FALHAS_SEGUIDAS:])


def _classe(b):
    if _duro(b):
        return "nao_da"
    s = _bstats(b)
    if s["n"] >= MIN_N and s["pok"] < TAXA_OK_MIN:
        return "nao_da"
    if s["n"] < MIN_N:
        return "sem_dado"
    if s["p1"] < TAXA_1A_MIN:
        return "precisa_ajuda"
    return "bom"


def _avaliar(regs, tipo, m, b0):
    """Devolve (usar, brief, effort, motivos)."""
    L = b0
    motivos = []
    if _classe(_balde(regs, tipo, m, b0)) == "sem_dado":
        for L2 in range(b0 + 1, 4):
            b2 = _balde(regs, tipo, m, L2)
            if _classe(b2) == "bom":
                dp = _bstats(b2)["de_primeira"]
                return True, L2, None, motivos + [
                    "sem prova com brief %d; provado com brief %d (%d/%d)" % (b0, L2, dp, len(b2))]
    while True:
        b = _balde(regs, tipo, m, L)
        s = _bstats(b)
        c = _classe(b)
        if c in ("sem_dado", "bom"):
            return True, L, None, motivos
        if c == "precisa_ajuda":
            if L >= 3:
                motivos.append("%s brief 3: de primeira %d/%d -> effort high" % (
                    m, s["de_primeira"], s["n"]))
                return True, 3, "high", motivos
            motivos.append("%s brief %d: de primeira %d/%d -> brief %d" % (
                m, L, s["de_primeira"], s["n"], L + 1))
            L += 1
        else:
            ok = s["de_primeira"] + s["corrigido"]
            if L >= 3:
                motivos.append("%s nao deu conta nem com brief 3: ok %d/%d" % (m, ok, s["n"]))
                return False, 3, None, motivos
            motivos.append("%s brief %d: ok %d/%d -> brief 3" % (m, L, ok, s["n"]))
            L = 3


def avisos_par(regs, tipo, m):
    par = _pares(regs, tipo, m)
    cont = {}
    for r in par:
        for k in set(_norm_erro(e) for e in r["erros"]):
            if k:
                cont[k] = cont.get(k, 0) + 1
    ordem = sorted(cont.items(), key=lambda kv: (-kv[1], kv[0]))
    out = []
    listados = set()
    com_erro = [r for r in par if any(e for e in r["erros"])]
    M = len(com_erro)
    por_classe = {}
    for r in com_erro:
        vistas = {}
        for e, c in zip(r["erros"], r["classes"]):
            if e and c != "outro":
                vistas[c] = e
        for c, det in vistas.items():
            ent = por_classe.setdefault(c, [0, ""])
            ent[0] += 1
            ent[1] = det   # registros em ordem: o ultimo a gravar e o mais recente
    for c, (N, ultimo) in sorted(por_classe.items(), key=lambda kv: (-kv[1][0], kv[0])):
        if N >= 2 and len(out) < MAX_AVISOS:
            msg = "cuidado: %d de %d entregas com erro foram de %s (ultimo: %s)" % (
                N, M, c, ultimo[:100])
            if CLASSES_ERRO[c][1]:
                msg += " -> no brief: " + CLASSES_ERRO[c][1]
            out.append(msg)
    for k, v in ordem:
        if v >= 2 and len(out) < MAX_AVISOS:
            out.append("cuidado: %s (%dx)" % (k, v))
            listados.add(k)
    modelo_regs = [r for r in regs if r["modelo"] == m
                   and r["resultado"] != "anulado"][-JANELA_GERAL:]
    g = {}
    for r in modelo_regs:
        for k in set(_norm_erro(e) for e in r["erros"]):
            if k:
                g[k] = g.get(k, 0) + 1
    for k, v in sorted(g.items(), key=lambda kv: (-kv[1], kv[0])):
        if v >= 3 and k not in listados:
            out.append("geral: %s (%dx)" % (k, v))
            break
    return out


def licoes_par(regs, tipo, m):
    grupos = {}
    for i, r in enumerate(_pares(regs, tipo, m)):
        if r["resultado"] not in ("de_primeira", "corrigido"):
            continue
        l = r["licao"].strip()
        if not l:
            continue
        k = l.lower()
        g = grupos.setdefault(k, {"n": 0, "i": 0, "txt": l})
        g["n"] += 1
        g["i"] = i
        g["txt"] = l
    ordem = sorted(grupos.values(), key=lambda g: (-g["n"], -g["i"]))[:3]
    return [("%s (%dx)" % (g["txt"], g["n"])) if g["n"] > 1 else g["txt"] for g in ordem]


def _stats_tipo(regs, tipo):
    out = {}
    for m in MODELOS:
        par = _pares(regs, tipo, m)
        if not par:
            continue
        s = _bstats(par)
        niveis = {}
        for L in (1, 2, 3):
            b = [r for r in par if r["brief"] == L]
            if b:
                niveis[str(L)] = _bstats(b)
        s["niveis"] = niveis
        out[m] = s
    return out


def rota_tipo(regs, tipo, agora=None):
    agora = agora or datetime.now().astimezone()
    d, b0 = PADRAO[tipo]
    idx = ESCADA.index(d)
    escolha = None  # (modelo, brief, effort, motivos)
    acum = []

    # 1) promocao
    for m in ESCADA[:idx]:
        for L in (1, 2, 3):
            b = _balde(regs, tipo, m, L)
            s = _bstats(b)
            if s["n"] >= MIN_N and s["p1"] >= TAXA_1A_PROMOVER and not _duro(b):
                escolha = (m, L, None, ["promovido: %s de primeira %d/%d com brief %d" % (
                    m, s["de_primeira"], s["n"], L)])
                break
        if escolha:
            break

    # 2) avaliar a partir do padrao
    if not escolha:
        for m in ESCADA[idx:]:
            usar, L, eff, mot = _avaliar(regs, tipo, m, b0)
            acum.extend(mot)
            if usar:
                escolha = (m, L, eff, acum)
                break

    # 3) todos reprovados
    if not escolha:
        escolha = ("chefe", None, None, acum + ["todos reprovados: o chefe faz"])

    modelo, brief, effort, motivos = escolha
    if not motivos:
        motivos = ["rota padrao, sem historico" if not any(
            r["tipo"] == tipo and r["resultado"] != "anulado" for r in regs)
                   else "rota padrao"]

    # experimento
    experimento = None
    abaixo = None
    if modelo == "chefe":
        abaixo = "opus"
    elif modelo != "haiku":
        abaixo = ESCADA[ESCADA.index(modelo) - 1]
    if abaixo and tipo not in TIPOS_SEM_BARATO:
        b3 = _balde(regs, tipo, abaixo, 3)
        cl = _classe(b3)
        par_ab = _pares(regs, tipo, abaixo)
        if cl == "sem_dado":
            if tipo in TIPOS_EXPERIMENTO or par_ab:
                experimento = {"modelo": abaixo, "brief": 3,
                               "motivo": "sem prova com brief 3 (n=%d)" % len(b3)}
        elif par_ab:
            dt = _parse_ts(par_ab[-1]["ts"])
            if dt is not None and agora - dt >= timedelta(days=RETESTE_DIAS):
                experimento = {"modelo": abaixo, "brief": 3,
                               "motivo": "ultimo teste ha %d dias: retestar" % (agora - dt).days}
    if (experimento is None and abaixo and tipo in TIPOS_EXP_FORTE
            and modelo in ("sonnet", "opus") and brief):
        # prova forte = o par inteiro OU um nivel de brief sozinho (um registro solto de outro nivel nao dilui a prova)
        cands = ([dict(_bstats(_pares(regs, tipo, modelo)), de="todos os briefs")]
                 + [dict(_bstats(_balde(regs, tipo, modelo, L)), de="brief %d" % L) for L in (1, 2, 3)])
        fortes = [c for c in cands
                  if c["n"] >= EXP_FORTE_N and c["de_primeira"] / float(c["n"]) >= EXP_FORTE_TAXA]
        sf = max(fortes, key=lambda c: (c["de_primeira"] / float(c["n"]), c["n"])) if fortes else None
        if sf is not None and _classe(_balde(regs, tipo, abaixo, 3)) == "sem_dado":
            experimento = {"modelo": abaixo, "brief": 3,
                           "motivo": "%s acerta %d/%d de primeira (%s): testar %s na tarefa "
                                     "mais mecanica do tipo" % (
                                         modelo, sf["de_primeira"], sf["n"], sf["de"], abaixo)}
    if EXPERIMENTAR_BRIEF_MENOR and experimento is None and modelo != "chefe" and brief and brief >= 2:
        b = _balde(regs, tipo, modelo, brief)
        s = _bstats(b)
        if (s["n"] >= BRIEF_MENOR_N and s["p1"] >= BRIEF_MENOR_TAXA
                and _classe(_balde(regs, tipo, modelo, brief - 1)) == "sem_dado"):
            experimento = {"modelo": modelo, "brief": brief - 1,
                           "motivo": "acerta com brief %d (%d/%d): testar com menos detalhe" % (
                               brief, s["de_primeira"], s["n"])}
    if experimento:
        experimento["avisos"] = avisos_par(regs, tipo, experimento["modelo"])
        experimento["feitos"] = len([r for r in _pares(regs, tipo, experimento["modelo"])
                                     if r.get("experimento") is True
                                     and r["brief"] == experimento["brief"]])
        experimento["meta"] = EXP_META

    ex = p_exemplo(tipo, modelo)
    return {
        "tipo": tipo,
        "modelo": modelo,
        "brief": brief,
        "effort": effort,
        "motivo": "; ".join(motivos),
        "experimento": experimento,
        "avisos": avisos_par(regs, tipo, modelo),
        "licoes": licoes_par(regs, tipo, modelo),
        "exemplo": ex if os.path.exists(ex) else None,
        "stats": _stats_tipo(regs, tipo),
    }


def todas_rotas(regs, tipo=None):
    return [rota_tipo(regs, t) for t in ([tipo] if tipo else TIPOS)]


def _fmt_stats(stats):
    partes = []
    for m, s in stats.items():
        niv = []
        for L, b in sorted(s["niveis"].items()):
            t = "b%s 1a %d/%d ok %d/%d" % (
                L, b["de_primeira"], b["n"], b["de_primeira"] + b["corrigido"], b["n"])
            if b.get("tok_med") is not None:
                t += " ~%dk" % int(round(b["tok_med"] / 1000.0))
            niv.append(t)
        partes.append("%s %s" % (m, "; ".join(niv)))
    return " | ".join(partes)


def texto_rota(r):
    if r["modelo"] == "chefe":
        L = ["%s -> chefe faz direto (%s)" % (r["tipo"], r["motivo"])]
    else:
        cab = "%s -> %s brief %d" % (r["tipo"], r["modelo"], r["brief"])
        if r["effort"]:
            cab += " effort %s" % r["effort"]
        L = [cab + " (%s)" % r["motivo"]]
    for a in r["avisos"]:
        L.append("  " + a)
    for l in r["licoes"]:
        L.append("  licao: " + l)
    e = r["experimento"]
    if e:
        L.append("  experimento: %s brief %d (%s; feitos %d de %d)" % (
            e["modelo"], e["brief"], e["motivo"], e["feitos"], e["meta"]))
        for a in e.get("avisos", []):
            L.append("    " + a)
    if r["exemplo"]:
        L.append("  exemplo: " + r["exemplo"])
    if r["stats"]:
        L.append("  stats: " + _fmt_stats(r["stats"]))
    return L


def cmd_ficha(args):
    regs = ler_registro()
    rotas = todas_rotas(regs, args.tipo)
    if args.json:
        print(json.dumps(rotas, ensure_ascii=False, indent=2))
    else:
        for r in rotas:
            for l in texto_rota(r):
                print(l)
    return 0


# ----------------------------------------------------------------------------
# Resumo
# ----------------------------------------------------------------------------
def _fmt_mi(n):
    v = n / 1e6
    s = ("%.2f" % v) if (v < 1 and "%.2f" % v != "1.00") else ("%.1f" % v)
    return s.replace(".", ",") + "M"


def cmd_resumo(args):
    try:
        seg = _parse_janela(args.desde)
    except ValueError as e:
        print("erro: %s" % e, file=sys.stderr)
        return 13
    sessao = None if args.todas else sessao_atual()
    limite = datetime.now().astimezone() - timedelta(seconds=seg)
    sel = []
    for r in ler_registro():
        dt = _parse_ts(r["ts"])
        if dt is None or dt < limite:
            continue
        if sessao and r.get("sessao") != sessao:
            continue
        sel.append(r)
    if not sel:
        print("operarios: nenhuma tarefa registrada")
        return 10
    validos = [r for r in sel if r["resultado"] != "anulado"]
    K = len(sel) - len(validos)
    c = {k: 0 for k in RESULTADOS}
    por = {}
    for r in validos:
        c[r["resultado"]] += 1
        t = por.setdefault(r["modelo"], [0, 0])
        t[1] += 1
        if r["resultado"] == "de_primeira":
            t[0] += 1
    ordem = [m for m in MODELOS if m in por]
    mods = "; ".join("%s %d/%d de primeira" % (m, por[m][0], por[m][1]) for m in ordem)
    cabeca = "operarios: %d tarefas, %d de primeira, %d corrigidas, %d escaladas, %d falharam" % (
        len(validos), c["de_primeira"], c["corrigido"], c["escalado"], c["falhou"])
    if K > 0:
        cabeca += ", %d anuladas" % K
    partes = [cabeca]
    if mods:
        partes.append(mods)
    somas = {}
    for r in validos:
        t = _tok_saida(r)
        if t is not None:
            somas[r["modelo"]] = somas.get(r["modelo"], 0) + t
    if somas:
        partes.append("saida: " + PONTO.join(
            "%s %s" % (m, _fmt_mi(somas[m])) for m in MODELOS if m in somas))
    partes.append("haiku fez %d de %d" % (
        len([r for r in validos if r["modelo"] == "haiku"]), len(validos)))
    print(" | ".join(partes))
    if args.por_frente:
        grupos = {}
        for r in validos:
            f = r.get("frente")
            f = f if isinstance(f, str) and f else "(sem frente)"
            g = grupos.setdefault(f, {"n": 0, "dp": 0, "corr": 0, "falh": 0, "tok": 0})
            g["n"] += 1
            if r["resultado"] == "de_primeira":
                g["dp"] += 1
            elif r["resultado"] == "corrigido":
                g["corr"] += 1
            elif r["resultado"] == "falhou":
                g["falh"] += 1
            t = _tok_saida(r)
            if t is not None:
                g["tok"] += t
                g["com_tok"] = True
        nomes = sorted(k for k in grupos if k != "(sem frente)")
        if "(sem frente)" in grupos:
            nomes.append("(sem frente)")
        for f in nomes:
            g = grupos[f]
            # sem nenhum registro com tokens contados por resposta: "-" (nao e custo zero)
            print("  %s: %d tarefas, %d de primeira, %d corrigidas, %d falharam, saida %s" % (
                f, g["n"], g["dp"], g["corr"], g["falh"],
                _fmt_mi(g["tok"]) if g.get("com_tok") else "-"))
    return 0


# ----------------------------------------------------------------------------
# Atualizar nota
# ----------------------------------------------------------------------------
CABECALHO = (
    "---\n"
    "name: fichas-operarios\n"
    "description: \"Fichas dos operarios Haiku/Sonnet/Opus da skill orquestrador: rota atual por tipo "
    "de tarefa, taxa de acerto, avisos e licoes, geradas do registro\"\n"
    "metadata:\n"
    "  type: reference\n"
    "  origem: auto\n"
    "---\n\n"
    "# Fichas dos operarios (skill orquestrador)\n\n"
    "O trecho entre os marcadores abaixo e gerado por `operarios.py atualizar`.\n"
    "Escreva notas a mao fora dos marcadores: elas sao preservadas.\n\n"
)

PONTO = " \u00b7 "


def _cel(stats, m):
    s = stats.get(m)
    if not s or not s["niveis"]:
        return "-"
    return PONTO.join("b%s %d/%d" % (L, b["de_primeira"], b["n"])
                      for L, b in sorted(s["niveis"].items()))


def gerar_bloco(regs):
    rotas = todas_rotas(regs)
    agora = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    L = []
    L.append("Gerado em %s - %d registros." % (agora, len(regs)))
    L.append("")
    L.append("| tipo | rota atual | haiku (de primeira/n) | sonnet (de primeira/n) | opus (de primeira/n) | avisos |")
    L.append("|---|---|---|---|---|---|")
    for r in rotas:
        if r["modelo"] == "chefe":
            rota = "chefe"
        else:
            rota = "%s b%d" % (r["modelo"], r["brief"])
            if r["effort"]:
                rota += " %s" % r["effort"]
        av = _limpar("; ".join(r["avisos"])) or "-"
        L.append("| %s | %s | %s | %s | %s | %s |" % (
            r["tipo"], _limpar(rota), _limpar(_cel(r["stats"], "haiku")),
            _limpar(_cel(r["stats"], "sonnet")), _limpar(_cel(r["stats"], "opus")), av))
    L.append("")
    L.append("## O que funciona")
    L.append("")
    algum = False
    for r in rotas:
        if r["licoes"]:
            algum = True
            L.append("### %s (%s)" % (r["tipo"], r["modelo"]))
            for l in r["licoes"]:
                L.append("- " + _limpar(l))
            L.append("")
    if not algum:
        L.append("Sem licoes registradas ainda.")
        L.append("")
    L.append("## Exemplos de brief")
    L.append("")
    achou = False
    try:
        for nome in sorted(os.listdir(p_exemplos())):
            if nome.endswith(".md"):
                achou = True
                L.append("- " + _limpar(os.path.join(p_exemplos(), nome)))
    except OSError:
        pass
    if not achou:
        L.append("Nenhum exemplo salvo ainda.")
    L.append("")
    return "\n".join(L)


def _gravar_atomico(path, conteudo):
    pasta = os.path.dirname(os.path.abspath(path))
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ficha-", suffix=".tmp", dir=pasta)
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_atualizar(args):
    path = p_ficha()
    if not path:
        print("aviso: ORQ_FICHA nao definida; ficha nao gravada (defina ORQ_FICHA com o caminho "
              "de um arquivo .md)", file=sys.stderr)
        return 0
    regs = ler_registro()
    bloco = gerar_bloco(regs)
    criado = False
    if os.path.exists(path):
        with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
            atual = f.read()
        crlf = "\r\n" in atual
        nl = "\r\n" if crlf else "\n"
        trecho = MARC_INI + "\n" + bloco + "\n" + MARC_FIM
        if crlf:
            trecho = trecho.replace("\n", "\r\n")
        ni, nf = atual.count(MARC_INI), atual.count(MARC_FIM)
        if ni == 0 and nf == 0:
            sep = "" if (atual.endswith("\n") or not atual) else nl
            conteudo = atual + sep + nl + trecho + nl
        elif ni == 1 and nf == 1 and atual.find(MARC_INI) < atual.find(MARC_FIM):
            i = atual.find(MARC_INI)
            j = atual.find(MARC_FIM) + len(MARC_FIM)
            conteudo = atual[:i] + trecho + atual[j:]
        else:
            print("erro: marcadores da nota inconsistentes (%d de inicio, %d de fim, ou fora de "
                  "ordem) em %s; corrija a mao e rode de novo. Nada foi gravado." % (ni, nf, path),
                  file=sys.stderr)
            return 13
    else:
        conteudo = CABECALHO + MARC_INI + "\n" + bloco + "\n" + MARC_FIM + "\n"
        criado = True
    try:
        _gravar_atomico(path, conteudo)
    except OSError as e:
        print("erro: nao consegui gravar a ficha: %s" % e, file=sys.stderr)
        return 13
    print("ficha %s: %s (%d registros)" % ("criada" if criado else "atualizada", path, len(regs)))
    return 0


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write("erro: %s\n" % message)
        sys.exit(13)


def montar_parser():
    ap = Parser(prog="operarios.py", description="Motor da skill orquestrador.")
    sub = ap.add_subparsers(dest="cmd", parser_class=Parser)
    sub.required = True

    s = sub.add_parser("status", help="canario e caminhos")
    s.set_defaults(fn=cmd_status)

    r = sub.add_parser(
        "registrar", help="grava o resultado de um operario",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="classes de erro (--erro \"classe: detalhe\"):\n" + "\n".join(
            "  %s: %s" % (c, v[0]) for c, v in CLASSES_ERRO.items()))
    r.add_argument("--tipo", choices=TIPOS)
    r.add_argument("--modelo", choices=MODELOS)
    r.add_argument("--resultado", required=True, choices=RESULTADOS,
                   help="anulado = nao rodou ou foi barrada (fica no registro, fora das "
                        "estatisticas)")
    r.add_argument("--frente", help="frente da obra (ate %d chars)" % MAX_FRENTE)
    r.add_argument("--rodadas", required=True, type=int)
    r.add_argument("--brief", required=True, type=int)
    r.add_argument("--effort", choices=EFFORTS)
    r.add_argument("--erro", action="append",
                   help='repetivel; formato "classe: detalhe" (classes abaixo)')
    r.add_argument("--licao")
    r.add_argument("--projeto")
    r.add_argument("--tarefa")
    r.add_argument("--experimento", action="store_true")
    r.add_argument("--tokens", type=int)
    r.add_argument("--agente", help="descricao do subagente (igual ou prefixo); deduz tipo, "
                                    "modelo real e tokens do transcript")
    r.set_defaults(fn=cmd_registrar)

    f = sub.add_parser("ficha", help="rota recomendada por tipo (fable e aceito no registro e "
                                     "aparece nas stats, mas nao entra na rota)")
    f.add_argument("--tipo", choices=TIPOS)
    f.add_argument("--json", action="store_true")
    f.set_defaults(fn=cmd_ficha)

    c = sub.add_parser("conferir", help="confere qual modelo cada subagente rodou")
    c.add_argument("--desde", default="12h", help="Nh ou Nd (padrao 12h)")
    c.add_argument("--json", action="store_true")
    c.add_argument("--todas", action="store_true", help="todas as sessoes (padrao: sessao atual)")
    c.add_argument("--sessao", help="id de uma sessao especifica")
    c.set_defaults(fn=cmd_conferir)

    u = sub.add_parser("resumo", help="1 linha com os registros da janela")
    u.add_argument("--desde", default="12h", help="Nh ou Nd (padrao 12h)")
    u.add_argument("--todas", action="store_true", help="todas as sessoes (padrao: sessao atual)")
    u.add_argument("--por-frente", action="store_true", help="1 linha por frente")
    u.set_defaults(fn=cmd_resumo)

    a = sub.add_parser("atualizar", help="grava a nota da ficha")
    a.set_defaults(fn=cmd_atualizar)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = montar_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
