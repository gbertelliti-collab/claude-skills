#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""operarios.py - motor da skill orquestrador.

Registra como cada operario (haiku/sonnet/opus) se saiu em cada tarefa e devolve
uma ficha com a rota recomendada aprendida do historico.

Comandos: status, registrar, ficha, conferir, retomar, resumo, atualizar, atualizacao.
ORQ_SEM_AVISO_ATUALIZACAO=1 cala o aviso de atualizacao automatica desligada.
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
import shutil
import statistics
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta

# ----------------------------------------------------------------------------
# Constantes ajustaveis
# ----------------------------------------------------------------------------
TIPOS = ["busca", "leitura", "pesquisa-web", "edicao-mecanica", "edicao-logica",
         "teste", "dados-sql", "front", "design", "debug", "texto", "revisao", "coordenacao", "outro"]
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
    "design": ("opus", 3),
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
TIPOS_SEM_DESCIDA = {"design"}   # tela que o dono julga pelo olho: nunca promove nem experimenta modelo menor
REGRA_TIPO = {
    "design": ("design nao se fatia nem desce de modelo: o chefe desenha a 1a tela com a skill de design "
               "aberta; se delegar, UM autor por tela (orq-designer, opus) com a referencia em maos e "
               "prova por print em desktop e celular; operario sonnet so liga dados (tipo front) depois "
               "do visual aprovado"),
}
TIPOS_ESCRITA = [t for t in TIPOS if t not in ("busca", "leitura", "pesquisa-web", "revisao", "coordenacao")]
GRANDE_RESPOSTAS = 30   # respostas ate a 1a entrega a partir das quais a tarefa de escrita e "grande"
PEQUENA_RESPOSTAS = 15  # abaixo disso a tarefa e candidata ao experimento no modelo mais barato
TAMANHO_MIN_N = 8
CLASSE_TIPO_MIN = 3     # entregas com erro da mesma classe, no tipo, pra virar aviso
TAMANHO_DIF = 0.15
JANELA_TAMANHO = 200
_PREFIXOS_HARNESS = ("<system-reminder>", "[handback-send-enforce]", "[Image:", "This session is being continued")
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


def _eh_mensagem_nova(d):
    """linha "user" que e mensagem nova pro agente (brief ou correcao), nao resultado de ferramenta."""
    msg = d.get("message")
    c = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(c, str):
        texto = c.strip()
    elif isinstance(c, list):
        partes = []
        for b in c:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_result":
                return False
            if b.get("type") == "text" and isinstance(b.get("text"), str):
                partes.append(b["text"])
        if not any(isinstance(b, dict) and b.get("type") == "text" for b in c):
            return False
        texto = " ".join(partes).strip()
    else:
        return False
    if not isinstance(c, list) and not texto:
        return False
    return not texto.startswith(_PREFIXOS_HARNESS)


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
    novas = 0           # mensagens novas (brief + correcoes) vistas ate agora
    chaves_1a = set()   # respostas vistas antes da 2a mensagem nova
    try:
        with io.open(jsonl, "r", encoding="utf-8", errors="replace") as f:
            for n, linha in enumerate(f):
                linha = linha.strip()
                if not linha:
                    continue
                eh_assist = '"assistant"' in linha
                if not eh_assist and not ('"user"' in linha and '"tool_result"' not in linha):
                    continue
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                if d.get("type") == "user":
                    if _eh_mensagem_nova(d):
                        novas += 1
                    continue
                if d.get("type") != "assistant":
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
                if novas < 2:
                    chaves_1a.add(chave)
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
        "respostas_1a": len(chaves_1a) if novas >= 2 else len(resp),
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


def _sessao_do_hook():
    """session_id do JSON em stdin (so se nao for terminal); erro = None."""
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        bruto = getattr(sys.stdin, "buffer", None)
        if bruto is not None:   # bytes: o encoding padrao do Windows quebra em caminho com acento
            texto = bruto.read().decode("utf-8", "replace")
        else:
            texto = sys.stdin.read()
        d = json.loads(texto)
        s = d.get("session_id") if isinstance(d, dict) else None
        return s if isinstance(s, str) and s else None
    except Exception:
        return None


_TAG_OPERARIO = re.compile(r"^\s*\[(?:%s)[:\]]" % "|".join(ALIASES))


def _e_operario(meta_path, descricao):
    """So conta o que o orquestrador despachou: papel orq-* (com ou sem prefixo de plugin) ou
    descricao no formato [modelo:tipo]. Subagente comum do usuario (Explore, general-purpose
    sem a etiqueta) fica de fora: o hook roda em toda sessao de quem instalou o plugin."""
    try:
        meta = _ler_json(meta_path)
    except Exception:
        meta = {}
    papel = meta.get("agentType") if isinstance(meta, dict) else None
    if isinstance(papel, str) and papel.rsplit(":", 1)[-1].startswith("orq-"):
        return True
    return bool(_TAG_OPERARIO.match(descricao or ""))


def cmd_retomar(args):
    if args.hook:
        try:
            return _retomar(args)
        except Exception:
            return 0
    return _retomar(args)


def _retomar(args):
    hook = args.hook
    try:
        seg = _parse_janela(args.desde)
    except ValueError as e:
        if hook:
            return 0
        print("erro: %s" % e, file=sys.stderr)
        return 13
    sessao = args.sessao
    if not sessao and hook:
        sessao = _sessao_do_hook()
    if not sessao:
        sessao = sessao_atual()
    if not sessao:
        if hook:
            return 0
        print("erro: sem sessao (use --sessao ID ou rode dentro do Claude Code)", file=sys.stderr)
        return 2
    metas = _achar_metas(p_projects(), time.time() - seg, sessao)
    ags = []
    for m in metas:
        a = analisar_agente(m)
        if _e_operario(m, a.get("descricao")):
            ags.append(a)
    if not ags:
        if hook:
            return 0
        if args.json:
            print(json.dumps({"sessao": sessao, "operarios": 0, "registrados": 0,
                              "sem_registro": [], "resultados": {}}))
        else:
            print("nenhum operario encontrado na sessao %s (janela de %s)" % (sessao, args.desde))
        return 10
    regs = [r for r in ler_registro() if r.get("sessao") == sessao]
    ids_reg = set(r.get("agente") for r in regs if r.get("agente"))
    ags.sort(key=lambda a: a["agente"])
    sem = [a for a in ags if a["agente"] not in ids_reg]
    n_reg = len(ags) - len(sem)
    cont = {}
    for r in regs:
        cont[r["resultado"]] = cont.get(r["resultado"], 0) + 1
    res = [(k, cont[k]) for k in RESULTADOS if cont.get(k, 0) > 0]
    if args.json:
        print(json.dumps({
            "sessao": sessao, "operarios": len(ags), "registrados": n_reg,
            "sem_registro": [{"agente": a["agente"], "descricao": a["descricao"],
                              "reais": a["reais"], "respostas": a["respostas"]} for a in sem],
            "resultados": dict(res)}, ensure_ascii=False))
        return 0
    n = len(ags)
    print("orquestrador: esta sessao ja despachou %d operario%s (%d registrados, %d sem registro)." % (
        n, "" if n == 1 else "s", n_reg, len(sem)))
    if sem:
        print("sem registro (confira a entrega e registre; o que nao rodou e anulado):")
        for a in sem[:15]:
            print("  - %s | modelo real: %s | %d respostas" % (
                a["descricao"] or "(sem descricao)", ",".join(a["reais"]) or "-", a["respostas"]))
        if len(sem) > 15:
            print("  ... e mais %d" % (len(sem) - 15))
    if res:
        print("registrados: " + ", ".join("%d %s" % (v, k) for k, v in res))
    print("proximo passo do chefe: reler o arquivo de estado se houver, rodar `conferir` e dizer "
          "ao usuario quem esta vivo e o que falta.")
    return 0


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


def _classe_do_erro(e):
    """Devolve (classe, detalhe) de um --erro "classe: detalhe", ou (None, e) sem classe."""
    m = re.match(r"^\s*([^\W\d_]+)(?:[-_][^:\s]{0,30})?\s*:(.*)$", e, re.S)
    if not m:
        return None, e
    tok = "".join(ch for ch in unicodedata.normalize("NFD", m.group(1).lower())
                  if unicodedata.category(ch) != "Mn")
    if tok in _NOMES_CLASSE:
        return tok, m.group(2).strip() or e
    return None, e


def _bloco_reg(r, i_marca=None):
    out = ["%s %s %s %s %s" % (r.get("id", "-"), (r.get("ts") or "")[:10], r["modelo"],
                               r["tipo"], r.get("projeto") or "-")]
    for i, (c, e) in enumerate(zip(r["classes"], r["erros"]), 1):
        out.append("  [%d] %s: %s" % (i, c, e))
    return out


def cmd_reclassificar(args):
    if args.listar:
        achou = False
        for r in ler_registro():
            if "outro" in r["classes"]:
                achou = True
                print("\n".join(_bloco_reg(r)))
        if not achou:
            print("nenhum erro sem classe")
            return 10
        return 0
    classes = args.classe or []
    if not classes:
        print("erro: --id exige ao menos um --classe", file=sys.stderr)
        return 13
    reg = p_registro()
    if not os.path.exists(reg):
        print("erro: id nao encontrado: %s" % args.id, file=sys.stderr)
        return 13

    def trabalho():
        with io.open(reg, "r", encoding="utf-8-sig", newline="") as f:
            linhas = f.read().splitlines(keepends=True)
        alvo = None
        for i, ln in enumerate(linhas):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if isinstance(d, dict) and d.get("id") == args.id:
                alvo = (i, d)
                break
        if alvo is None:
            print("erro: id nao encontrado: %s" % args.id, file=sys.stderr)
            return 13
        i, d = alvo
        er = d.get("erros")
        if isinstance(er, str):
            er = [er]
        if not isinstance(er, list):
            er = []
        if len(er) != len(classes):
            atuais = d.get("classes") if isinstance(d.get("classes"), list) else []
            print("erro: o registro tem %d erro(s) e vieram %d classe(s):" % (len(er), len(classes)),
                  file=sys.stderr)
            for k, e in enumerate(er):
                c = atuais[k] if k < len(atuais) and isinstance(atuais[k], str) else "outro"
                print("  [%d] %s: %s" % (k + 1, c, e), file=sys.stderr)
            return 13
        ln = linhas[i]
        fim = ln[len(ln.rstrip("\r\n")):]
        d["classes"] = list(classes)
        shutil.copyfile(reg, reg + ".antes-de-reclassificar")
        linhas[i] = json.dumps(d, ensure_ascii=False) + fim
        _gravar_atomico(reg, "".join(linhas))
        nr = _norm_reg(d)
        if nr is None:
            nr = {"id": d.get("id"), "ts": d.get("ts") or "", "modelo": d.get("modelo"),
                  "tipo": d.get("tipo"), "projeto": d.get("projeto"),
                  "classes": list(classes), "erros": [str(x) for x in er]}
        nr.setdefault("id", d.get("id"))
        print("\n".join(_bloco_reg(nr)))
        return 0

    try:
        return _com_trava(reg + ".trava", trabalho)
    except (OSError, UnicodeError) as e:
        print("erro: nao consegui reescrever o registro: %s. Nada foi alterado." % e, file=sys.stderr)
        return 13


def cmd_reprovar(args):
    if bool(args.id) == bool(args.agente):
        print("erro: passe --id ou --agente (um dos dois, nao os dois). Nada foi alterado.",
              file=sys.stderr)
        return 13
    erros_in = args.erro or []
    if not erros_in:
        print("erro: reprovar exige ao menos um --erro \"classe: detalhe\". Nada foi alterado.",
              file=sys.stderr)
        return 13
    for e in erros_in:
        if _classe_do_erro(e)[0] is None:
            print('erro: --erro sem classe: "%s"' % e[:60], file=sys.stderr)
            print('use "classe: detalhe", um erro por --erro. Classes:', file=sys.stderr)
            for c, v in CLASSES_ERRO.items():
                print("  %s: %s" % (c, v[0]), file=sys.stderr)
            print('"outro: detalhe" so quando nenhuma couber. Nada foi alterado.', file=sys.stderr)
            return 13
    novos, novas_classes = [], []
    for e in erros_in:
        classe, det = _classe_do_erro(e)
        t, _cls = redigir(det)
        novos.append(_trunc(_limpar(t), MAX_ERRO))
        novas_classes.append(classe)
    if args.id:
        alvo_txt = "id %s" % args.id
    else:
        alvo_txt = "tarefa %s" % args.agente
        t, _cls = redigir(args.agente)
        agente_limpo = _trunc(_limpar(t), MAX_TAREFA)
    reg = p_registro()
    if not os.path.exists(reg):
        print("erro: nao achei registro com %s" % alvo_txt, file=sys.stderr)
        return 13

    def trabalho():
        with io.open(reg, "r", encoding="utf-8-sig", newline="") as f:
            linhas = f.read().splitlines(keepends=True)
        alvo = None
        for i, ln in enumerate(linhas):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            if args.id:
                if d.get("id") == args.id:
                    alvo = (i, d)
                    break
            elif d.get("tarefa") in (args.agente, agente_limpo):
                alvo = (i, d)      # sem break: vale o mais recente
        if alvo is None:
            print("erro: nao achei registro com %s" % alvo_txt, file=sys.stderr)
            return 13
        i, d = alvo
        antes = d.get("resultado")
        if antes == "anulado":
            print("erro: tarefa anulada nao tem entrega pra reprovar", file=sys.stderr)
            return 13
        rod = d.get("rodadas")
        rod = rod if isinstance(rod, int) and not isinstance(rod, bool) else 0
        er = d.get("erros")
        if isinstance(er, str):
            er = [er]
        er = list(er) if isinstance(er, list) else []
        cl = d.get("classes")
        cl = list(cl) if isinstance(cl, list) else []
        for c in novas_classes:
            if c not in cl:
                cl.append(c)
        if antes == "de_primeira":
            d["resultado"] = "corrigido"
        d["rodadas"] = rod + 1
        d["erros"] = er + novos
        d["classes"] = cl
        d["reprovado"] = True
        ln = linhas[i]
        fim = ln[len(ln.rstrip("\r\n")):]
        shutil.copyfile(reg, reg + ".antes-de-reprovar")
        nova = json.dumps(d, ensure_ascii=False)
        linhas[i] = nova + fim
        _gravar_atomico(reg, "".join(linhas))
        print(nova)
        print("reprovado: %s %s %s %s -> %s (rodadas %d)" % (
            d.get("id", "-"), d.get("tipo"), d.get("modelo"), antes, d["resultado"], d["rodadas"]))
        return 0

    try:
        return _com_trava(reg + ".trava", trabalho)
    except (OSError, UnicodeError) as e:
        print("erro: nao consegui reescrever o registro: %s. Nada foi alterado." % e, file=sys.stderr)
        return 13


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
    for e in (args.erro or []):
        if _classe_do_erro(e)[0] is None:
            print('erro: --erro sem classe: "%s"' % e[:60], file=sys.stderr)
            print('use "classe: detalhe", um erro por --erro. Classes:', file=sys.stderr)
            for c, v in CLASSES_ERRO.items():
                print("  %s: %s" % (c, v[0]), file=sys.stderr)
            print('"outro: detalhe" so quando nenhuma couber. Nada foi gravado.', file=sys.stderr)
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
    ach, conf = getattr(args, "achados", None), getattr(args, "confirmados", None)
    if ach is not None or conf is not None:
        if tipo != "revisao":
            print("erro: --achados e --confirmados so valem para revisao", file=sys.stderr)
            return 13
        if (ach is not None and ach < 0) or (conf is not None and conf < 0):
            print("erro: --achados e --confirmados nao podem ser negativos", file=sys.stderr)
            return 13
        if conf is not None and ach is None:
            print("erro: --confirmados exige --achados", file=sys.stderr)
            return 13
        if conf is not None and conf > ach:
            print("erro: --confirmados nao pode passar de --achados", file=sys.stderr)
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
    avisou_pv = False
    for e in (args.erro or []):
        classe, det = _classe_do_erro(e)
        if ";" in det:
            avisou_pv = True
        erros.append(limpa(det, MAX_ERRO))
        classes_e.append(classe)
    if avisou_pv:
        print('AVISO: --erro com ";" parece juntar mais de um erro: registre um por --erro, '
              'cada um com a sua classe', file=sys.stderr)
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
    if ach is not None:
        rec["achados"] = ach
        if conf is not None:
            rec["confirmados"] = conf
    if args.tokens is not None:
        rec["tokens"] = args.tokens
    if sessao_atual():
        rec["sessao"] = sessao_atual()
    if info:
        rec["agente"] = info["agente"]
        rec["tokens_saida"] = info["tokens_saida"]
        rec["respostas"] = info["respostas"]
        r1 = info.get("respostas_1a")
        if args.rodadas == 0:
            rec["respostas_1a"] = info["respostas"]
        elif isinstance(r1, int) and not isinstance(r1, bool) and r1 < info["respostas"]:
            rec["respostas_1a"] = r1
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
    _avisos_registrar(ordenado, args)
    print(linha)
    return 0


def _avisos_registrar(rec, args):
    """3 avisos curtos em stderr depois de gravar; nunca derrubam o registrar."""
    ruim = ("corrigido", "escalado", "falhou")
    res, tipo, modelo = rec["resultado"], rec["tipo"], rec["modelo"]
    r1 = rec.get("respostas_1a")
    r1 = r1 if isinstance(r1, int) and not isinstance(r1, bool) else None
    try:
        if r1 is not None and r1 >= GRANDE_RESPOSTAS and tipo in TIPOS_ESCRITA and res in ruim:
            print("AVISO: tarefa grande (%d respostas ate a 1a entrega; a partir de %d a escrita "
                  "erra bem mais de primeira). Na proxima: um objetivo por tarefa."
                  % (r1, GRANDE_RESPOSTAS), file=sys.stderr)
    except Exception:
        pass
    try:
        if (res == "de_primeira" and not args.experimento and tipo in TIPOS_ESCRITA
                and modelo in ESCADA and r1 is not None and r1 < PEQUENA_RESPOSTAS):
            rota = rota_tipo(ler_registro(), tipo)
            exp = rota.get("experimento")
            if exp and exp["modelo"] in ESCADA and ESCADA.index(exp["modelo"]) < ESCADA.index(modelo):
                print("AVISO: tarefa pequena (%d respostas) de primeira em %s: a proxima parecida de %s "
                      "vale o experimento em %s brief %d (feitos %d de %d), registrando com --experimento."
                      % (r1, modelo, tipo, exp["modelo"], exp["brief"], exp["feitos"], exp["meta"]),
                      file=sys.stderr)
    except Exception:
        pass
    try:
        if res in ruim and not args.erro and not args.licao:
            print("AVISO: %s sem --erro e sem --licao: a ficha nao aprende com esta linha. "
                  "Erro do operario = --erro \"classe: detalhe\"; faltou no brief = --licao." % res,
                  file=sys.stderr)
    except Exception:
        pass
    try:
        if res == "de_primeira" and tipo in ("front", "design"):
            print("AVISO: tela de primeira so vale se voce VIU o print (desktop e celular). O dono reprovou "
                  "depois? reprovar --id %s --erro \"visual: <o que ele disse>\"." % rec.get("id", "<id>"),
                  file=sys.stderr)
    except Exception:
        pass
    try:
        if tipo == "revisao" and res != "anulado" and getattr(args, "achados", None) is None:
            print("AVISO: revisao sem --achados/--confirmados: o placar do revisor fica sem dado "
                  "(0 e 0 tambem vale).", file=sys.stderr)
    except Exception:
        pass


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


def _do_brief(r):
    """rodada causada por brief incompleto: corrigido, sem erro do operario, com licao."""
    return (r["resultado"] == "corrigido" and not any(e for e in r["erros"])
            and bool(r["licao"].strip()))


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
        "do_brief": len([r for r in lista if _do_brief(r)]),
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
    # rodada que voltou por falta no brief nao julga o operario: o balde e avaliado sem ela,
    # com as mesmas regras de sempre (falha de verdade continua pesando inteira)
    j = [r for r in b if not _do_brief(r)]
    if _duro(j):
        return "nao_da"
    s = _bstats(j)
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
                    m, s["de_primeira"], s["n"] - s["do_brief"]))
                return True, 3, "high", motivos
            motivos.append("%s brief %d: de primeira %d/%d -> brief %d" % (
                m, L, s["de_primeira"], s["n"] - s["do_brief"], L + 1))
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


def faltou_par(regs, tipo, m):
    """licoes distintas dos registros devolvidos por falta no brief (mais recente primeiro, max 2)."""
    vistos = set()
    out = []
    for r in reversed(_pares(regs, tipo, m)):
        if not _do_brief(r):
            continue
        l = r["licao"].strip()
        if l.lower() in vistos:
            continue
        vistos.add(l.lower())
        out.append(l)
        if len(out) >= 2:
            break
    return out


def classe_do_tipo(regs, tipo):
    """Classe de erro mais comum no TIPO, somando todos os modelos: trocar o modelo da rota
    nao apaga o que o tipo de tarefa ja ensinou. Devolve (classe, n, com_erro) ou None."""
    rs = [r for r in regs if r["tipo"] == tipo and r["resultado"] != "anulado"][-JANELA_GERAL:]
    com_erro = 0
    cont = {}
    for r in rs:
        if not any(e for e in r["erros"]):
            continue
        com_erro += 1
        for c in set(c for e, c in zip(r["erros"], r["classes"]) if e and c != "outro"):
            cont[c] = cont.get(c, 0) + 1
    if not cont:
        return None
    c, n = sorted(cont.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    if n < CLASSE_TIPO_MIN:
        return None
    return c, n, com_erro


def avisos_rota(regs, tipo, m):
    """Avisos do par (tipo, modelo) mais, se couber, o da classe mais comum no tipo."""
    out = avisos_par(regs, tipo, m)
    ct = classe_do_tipo(regs, tipo)
    if ct and len(out) < MAX_AVISOS and not any((" foram de %s " % ct[0]) in a for a in out):
        msg = "no tipo: %d de %d entregas com erro foram de %s, somando os modelos" % (
            ct[1], ct[2], ct[0])
        if CLASSES_ERRO[ct[0]][1]:
            msg += " -> no brief: " + CLASSES_ERRO[ct[0]][1]
        out.append(msg)
    return out


def licoes_par(regs, tipo, m):
    grupos = {}
    for i, r in enumerate(_pares(regs, tipo, m)):
        if r["resultado"] not in ("de_primeira", "corrigido"):
            continue
        if _do_brief(r):
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
        n_rev = ach = conf = 0
        for r in par:
            a, c = r.get("achados"), r.get("confirmados")
            if (isinstance(a, int) and not isinstance(a, bool)
                    and isinstance(c, int) and not isinstance(c, bool)):
                n_rev += 1
                ach += a
                conf += c
        s["placar"] = [n_rev, ach, conf]
        out[m] = s
    return out


def rota_tipo(regs, tipo, agora=None):
    agora = agora or datetime.now().astimezone()
    d, b0 = PADRAO[tipo]
    idx = ESCADA.index(d)
    escolha = None  # (modelo, brief, effort, motivos)
    acum = []

    # 1) promocao
    for m in ([] if tipo in TIPOS_SEM_DESCIDA else ESCADA[:idx]):
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
    if tipo in TIPOS_SEM_DESCIDA:
        abaixo = None
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
    if (EXPERIMENTAR_BRIEF_MENOR and experimento is None and modelo != "chefe" and brief and brief >= 2
            and tipo not in TIPOS_SEM_DESCIDA):
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
        "regra": REGRA_TIPO.get(tipo),
        "avisos": avisos_rota(regs, tipo, modelo),
        "licoes": licoes_par(regs, tipo, modelo),
        "faltou": faltou_par(regs, tipo, modelo),
        "do_brief": [len([r for r in _pares(regs, tipo, modelo) if _do_brief(r)]),
                     len(_pares(regs, tipo, modelo))],
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
        t = "%s %s" % (m, "; ".join(niv))
        pl = s.get("placar")
        if pl and pl[0] > 0:
            t += " achados %d confirmados %d em %d revisoes" % (pl[1], pl[2], pl[0])
        partes.append(t)
    return " | ".join(partes)


def tamanho_geral(regs):
    """de_primeira da escrita pequena x grande, pelas respostas ate a 1a entrega."""
    lista = []
    for r in regs:
        v = r.get("respostas_1a")
        if (r["tipo"] in TIPOS_ESCRITA and r["resultado"] != "anulado"
                and isinstance(v, int) and not isinstance(v, bool)):
            lista.append(r)
    lista = lista[-JANELA_TAMANHO:]
    peq = [r for r in lista if r["respostas_1a"] < GRANDE_RESPOSTAS]
    gra = [r for r in lista if r["respostas_1a"] >= GRANDE_RESPOSTAS]
    if len(peq) < TAMANHO_MIN_N or len(gra) < TAMANHO_MIN_N:
        return None
    dp = len([r for r in peq if r["resultado"] == "de_primeira"])
    dg = len([r for r in gra if r["resultado"] == "de_primeira"])
    if dp / float(len(peq)) - dg / float(len(gra)) >= TAMANHO_DIF - 1e-9:
        return {"corte": GRANDE_RESPOSTAS, "peq": [dp, len(peq)], "gra": [dg, len(gra)]}
    return None


def texto_tamanho(t):
    return ("tamanho: escrita que o operario fecha em menos de %d respostas passa de primeira "
            "%d/%d; com %d ou mais, %d/%d -> um objetivo por tarefa; a que nao cabe vira duas" % (
                t["corte"], t["peq"][0], t["peq"][1], t["corte"], t["gra"][0], t["gra"][1]))


def texto_rota(r):
    if r["modelo"] == "chefe":
        L = ["%s -> chefe faz direto (%s)" % (r["tipo"], r["motivo"])]
    else:
        cab = "%s -> %s brief %d" % (r["tipo"], r["modelo"], r["brief"])
        if r["effort"]:
            cab += " effort %s" % r["effort"]
        L = [cab + " (%s)" % r["motivo"]]
    if r.get("regra"):
        L.append("  regra: " + r["regra"])
    for a in r["avisos"]:
        L.append("  " + a)
    if r["do_brief"][0] >= 2:
        L.append("  brief: %d das ultimas %d entregas voltaram por falta no brief "
                 "(nao conta contra o modelo)" % (r["do_brief"][0], r["do_brief"][1]))
    for f in r["faltou"]:
        L.append("  faltou no brief: " + f)
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
        t = tamanho_geral(regs)
        if t is not None and (args.tipo is None or args.tipo in TIPOS_ESCRITA):
            print(texto_tamanho(t))
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
    forte = [r for r in validos if r["modelo"] in ("opus", "fable") and r["tipo"] in TIPOS_ESCRITA]
    if forte:
        rot = "+".join(m for m in ("opus", "fable") if any(r["modelo"] == m for r in forte))
        toks = [_tok_saida(r) for r in forte]
        toks = [t for t in toks if t is not None]
        partes.append("%s em execucao: %d tarefas, %s de saida, %d de primeira" % (
            rot, len(forte), _fmt_mi(sum(toks)) if toks else "-",
            len([r for r in forte if r["resultado"] == "de_primeira"])))
    com_resp = [r for r in validos if r["tipo"] in TIPOS_ESCRITA
                and isinstance(r.get("respostas_1a"), int) and not isinstance(r.get("respostas_1a"), bool)]
    grandes = [r for r in com_resp if r["respostas_1a"] >= GRANDE_RESPOSTAS]
    if grandes:
        partes.append("grandes: %d de %d de escrita, %d de primeira" % (
            len(grandes), len(com_resp),
            len([r for r in grandes if r["resultado"] == "de_primeira"])))
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
    tam = tamanho_geral(regs)
    if tam is not None:
        L.append(texto_tamanho(tam))
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
        av = _limpar("; ".join((["regra: " + r["regra"]] if r.get("regra") else []) + r["avisos"])) or "-"
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
    faltas = [r for r in rotas if r["faltou"]]
    if faltas:
        L.append("## O que faltou no brief")
        L.append("")
        for r in faltas:
            L.append("### %s (%s)" % (r["tipo"], r["modelo"]))
            for f in r["faltou"]:
                L.append("- " + _limpar(f))
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


_TAG_DESPACHO = re.compile(r"^\s*\[\s*([^:\]\s]+)\s*:\s*([^\]]+?)\s*\]")


def _p_avisos_despacho():
    return os.path.join(os.path.dirname(os.path.abspath(p_registro())), "despacho-avisos.json")


def _ler_avisos_despacho():
    try:
        with io.open(_p_avisos_despacho(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _ja_avisou(sessao, chave):
    if not sessao:
        return False
    v = _ler_avisos_despacho().get(sessao)
    return isinstance(v, list) and chave in v


def _marcar_avisou(sessao, chave):
    if not sessao:
        return
    try:
        d = _ler_avisos_despacho()
        v = d.get(sessao)
        v = v if isinstance(v, list) else []
        if chave not in v:
            v.append(chave)
        d.pop(sessao, None)
        d[sessao] = v
        while len(d) > 30:
            d.pop(next(iter(d)))
        _gravar_atomico(_p_avisos_despacho(), json.dumps(d, ensure_ascii=False))
    except Exception:
        pass


_RE_PARECE_DESIGN = re.compile(
    r"\b(landing|home ?page|pagina inicial|tela inicial|pagina de vendas?|hero|redesenh\w*|redesign|"
    r"identidade visual|acabamento visual|visual novo|novo visual|layout novo|novo layout|"
    r"tela nova|nova tela|pagina nova|nova pagina)\b")


def _sem_acento(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(ch) != "Mn")


def avaliar_despacho(d, regs=None):
    """Avisos sobre o despacho de um operario. None = nao e despacho da skill; [] = tudo certo."""
    if not isinstance(d, dict) or d.get("tool_name") not in ("Agent", "Task"):
        return None
    ti = d.get("tool_input")
    if not isinstance(ti, dict):
        return None
    if (os.environ.get("ORQ_SEM_AVISO_DESPACHO") or "").strip().lower() in ("1", "true", "sim", "yes"):
        return None
    st = ti.get("subagent_type")
    papel = st.rsplit(":", 1)[-1] if isinstance(st, str) else ""
    e_orq = papel.startswith("orq-")
    desc = ti.get("description")
    desc = desc if isinstance(desc, str) else ""
    m = _TAG_DESPACHO.match(desc)
    tag_modelo = m.group(1).lower() if m else None
    tag_tipo = m.group(2).strip().lower() if m else None
    if not e_orq and (not m or tag_tipo not in TIPOS):
        return None
    mod = ti.get("model")
    modelo = mod.lower() if isinstance(mod, str) and mod else None
    prompt = ti.get("prompt")
    prompt = prompt if isinstance(prompt, str) else ""
    av = []
    if modelo is None:
        av.append("sem model: passe model explicito (haiku, sonnet ou opus) em todo despacho")
    if not m:
        av.append('descricao sem [modelo:tipo]: o registrar --agente e o conferir dependem dela '
                  '(ex.: "[sonnet:front] cartao na lista")')
    elif tag_tipo not in TIPOS:
        av.append('tipo "%s" nao existe. Tipos: %s' % (tag_tipo, ", ".join(TIPOS)))
    if tag_modelo and modelo and tag_modelo not in modelo:
        av.append("a descricao diz %s e o model e %s: acerte um dos dois" % (tag_modelo, modelo))
    escrita = tag_tipo in TIPOS_ESCRITA
    if escrita and tag_tipo != "debug" and papel in ("orq-leitor", "orq-revisor"):
        av.append("%s nao grava arquivo: tarefa de %s vai pra %s" % (
            papel, tag_tipo, "orq-designer" if tag_tipo == "design" else "orq-executor"))
    # executor sem etiqueta valida: o papel ja diz que a tarefa escreve
    if (escrita or (papel == "orq-executor" and tag_tipo not in TIPOS)) and "aceite" not in prompt.lower():
        av.append("brief sem ACEITE: escreva o comando ou a checagem que voce vai rodar na conferencia")
    efetivo = modelo if modelo is not None else tag_modelo
    valido = tag_tipo in TIPOS
    sessao = d.get("session_id")
    sessao = sessao if isinstance(sessao, str) and sessao else sessao_atual()
    pn = _sem_acento(prompt)
    dn = _sem_acento(desc)
    if tag_tipo == "design":
        fam = None
        for f in ("haiku", "sonnet", "opus", "fable"):
            if efetivo and f in efetivo:
                fam = f
                break
        if fam in ("haiku", "sonnet"):
            av.append("design em %s: tela que o dono julga pelo olho nao desce de modelo. O chefe desenha "
                      "com a skill de design aberta, ou UM operario opus por tela (orq-designer)" % fam)
        if papel == "orq-executor":
            av.append("orq-executor nao abre skill de design: design vai pra orq-designer (papel nao "
                      "existe na sessao: general-purpose opus com a ordem de ler o agents/orq-designer.md "
                      "do plugin orquestrador)")
        if not any(k in pn for k in ("print", "screenshot", "captura")):
            av.append("brief de design sem prova por print: o ACEITE e o print em desktop e celular, "
                      "visto pelo chefe ao lado da referencia")
        if not any(k in pn for k in ("referencia", "previa", "design.md", "mockup", "figma", "doop", "prototipo")):
            av.append("brief de design sem referencia visual: aponte a previa aprovada, o DESIGN.md ou "
                      "o print de referencia (caminho do arquivo)")
    if (tag_tipo == "front" and _RE_PARECE_DESIGN.search(dn + " " + pn[:800])
            and not _ja_avisou(sessao, "design:front")):
        av.append("parece design (tela que o dono vai julgar pelo olho) com etiqueta front: se for, o tipo "
                  "e design e a rota e outra (ficha --tipo design); front e ligar dados numa tela com o "
                  "visual ja aprovado")
        _marcar_avisou(sessao, "design:front")
    grande = None
    if efetivo:
        grande = "opus" if "opus" in efetivo else ("fable" if "fable" in efetivo else None)
    quer_f = bool(valido and escrita and grande)
    quer_g = bool(valido and efetivo)
    if quer_f or quer_g:
        if regs is None:
            regs = ler_registro()
        rota = rota_tipo(regs, tag_tipo)
        if quer_f and rota["modelo"] in ("haiku", "sonnet") and not _ja_avisou(sessao, "%s:%s" % (grande, tag_tipo)):
            av.append("%s em execucao: a ficha manda %s brief %d pra %s. Modelo maior nao compra "
                      "acerto: tarefa menor e brief nivel 3 primeiro. Se foi ordem do usuario ou "
                      "regra do projeto, siga." % (grande, rota["modelo"], rota["brief"], tag_tipo))
            _marcar_avisou(sessao, "%s:%s" % (grande, tag_tipo))
        ex = rota.get("experimento")
        if (quer_g and rota["modelo"] in ESCADA and rota["modelo"] in efetivo and ex
                and ex["modelo"] in ESCADA
                and ESCADA.index(ex["modelo"]) < ESCADA.index(rota["modelo"])
                and not _ja_avisou(sessao, "exp:%s" % tag_tipo)):
            av.append("experimento aberto em %s: %s brief %d (feitos %d de %d). Se a proxima tarefa "
                      "do tipo for das mais mecanicas, despache nela e registre com --experimento."
                      % (tag_tipo, ex["modelo"], ex["brief"], ex["feitos"], ex["meta"]))
            _marcar_avisou(sessao, "exp:%s" % tag_tipo)
    return av[:6]


def _despacho(args):
    bruto = getattr(sys.stdin, "buffer", None)
    if bruto is not None:   # bytes: o encoding padrao do Windows quebra em texto com acento
        texto = bruto.read().decode("utf-8", "replace")
    else:
        texto = sys.stdin.read()
    try:
        d = json.loads(texto) if texto.strip() else None
    except ValueError:
        d = None
    av = avaliar_despacho(d)
    if args.hook:
        if av:
            desc = ""
            if isinstance(d, dict) and isinstance(d.get("tool_input"), dict):
                x = d["tool_input"].get("description")
                desc = x if isinstance(x, str) else ""
            cab = 'orquestrador: aviso sobre o despacho "%s" (nao bloqueia; aplique no proximo):' % desc[:60]
            txt = cab + "\n" + "\n".join("- " + a for a in av)
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                     "additionalContext": txt}}))
        return 0
    if av is None:
        print("nao e despacho da skill")
    elif not av:
        print("despacho ok")
    else:
        for a in av:
            print(a)
    return 0


def cmd_despacho(args):
    if args.hook:
        try:
            return _despacho(args)
        except Exception:
            return 0
    return _despacho(args)


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
# Atualizacao automatica do plugin
# ----------------------------------------------------------------------------
# O Claude Code so liga a atualizacao automatica sozinho nos marketplaces oficiais; num marketplace
# de terceiro ela nasce desligada e quem publica nao consegue ligar por ninguem. Este bloco le a
# configuracao LOCAL (sem rede) pra dizer se quem instalou esta recebendo as versoes novas, avisa
# uma vez por semana (no maximo 3 vezes) e, so quando o usuario aceita, liga.
PLUGIN_NOME = "orquestrador"
AVISO_ATUALIZACAO_DIAS = 7
AVISO_ATUALIZACAO_MAX = 3
ENV_TRAVA_UPDATE = ("DISABLE_UPDATES", "DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")


def p_config():
    """Pasta de configuracao do Claude Code. ORQ_CLAUDE_DIR existe so pra teste."""
    return (os.environ.get("ORQ_CLAUDE_DIR") or os.environ.get("CLAUDE_CONFIG_DIR")
            or os.path.join(os.path.expanduser("~"), ".claude"))


def p_estado_atualizacao():
    return os.path.join(os.path.dirname(os.path.abspath(p_registro())), "atualizacao.json")


def _agora_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _env_ligada(nome):
    return (os.environ.get(nome) or "").strip().lower() not in ("", "0", "false", "no", "off")


def _json_ou_none(path):
    """Le um JSON de configuracao (aceita BOM). Devolve None se nao existe ou nao e objeto valido."""
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def _mesmo_caminho(a, b):
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError):
        return False


def _raiz_plugin(args):
    raiz = getattr(args, "raiz", None)
    if raiz:
        return os.path.abspath(raiz)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _marketplace_da_instalacao(raiz):
    """Nome do marketplace de onde ESTA copia do plugin foi instalada, ou None (copia solta,
    --plugin-dir, pasta de desenvolvimento): ai nao ha o que atualizar e ninguem e avisado."""
    cfg = p_config()
    inst = _json_ou_none(os.path.join(cfg, "plugins", "installed_plugins.json")) or {}
    plugins = inst.get("plugins")
    if isinstance(plugins, dict):
        for chave, entradas in plugins.items():
            if not isinstance(chave, str) or "@" not in chave or not isinstance(entradas, list):
                continue
            nome, mkt = chave.split("@", 1)
            if nome != PLUGIN_NOME or not mkt:
                continue
            for e in entradas:
                if isinstance(e, dict) and isinstance(e.get("installPath"), str) \
                        and _mesmo_caminho(e["installPath"], raiz):
                    return mkt
    # installed_plugins.json pode estar um passo atras (plugin atualizado no meio da sessao):
    # a pasta <config>/plugins/cache/<marketplace>/<plugin>/<versao> tambem diz de onde veio
    try:
        rel = os.path.relpath(os.path.realpath(raiz), os.path.realpath(os.path.join(cfg, "plugins", "cache")))
    except (OSError, ValueError):
        return None
    partes = rel.replace("\\", "/").split("/")
    if len(partes) == 3 and partes[0] not in ("..", ".", "") and partes[1] == PLUGIN_NOME:
        return partes[0]
    return None


def _arquivos_settings():
    """(rotulo, caminho) do que mais manda pro que menos manda."""
    if os.name == "nt":
        ger = os.path.join(os.environ.get("ProgramFiles") or "C:\\Program Files", "ClaudeCode",
                           "managed-settings.json")
    elif sys.platform == "darwin":
        ger = "/Library/Application Support/ClaudeCode/managed-settings.json"
    else:
        ger = "/etc/claude-code/managed-settings.json"
    cwd = os.getcwd()
    return [("gerenciado", ger),
            ("local do projeto", os.path.join(cwd, ".claude", "settings.local.json")),
            ("do projeto", os.path.join(cwd, ".claude", "settings.json")),
            ("do usuario", os.path.join(p_config(), "settings.json"))]


def _estado_auto_update(mkt):
    """(ligada, origem). Ordem da documentacao do Claude Code: `autoUpdate` na entrada do
    marketplace em `extraKnownMarketplaces` de um arquivo de settings; depois o `autoUpdate` do
    known_marketplaces.json (o que o botao do /plugin grava); depois o padrao (desligada)."""
    for rotulo, caminho in _arquivos_settings():
        dados = _json_ou_none(caminho) or {}
        ekm = dados.get("extraKnownMarketplaces")
        entrada = ekm.get(mkt) if isinstance(ekm, dict) else None
        if isinstance(entrada, dict) and isinstance(entrada.get("autoUpdate"), bool):
            return entrada["autoUpdate"], "settings " + rotulo
    conhecidos = _json_ou_none(os.path.join(p_config(), "plugins", "known_marketplaces.json")) or {}
    entrada = conhecidos.get(mkt)
    if isinstance(entrada, dict) and isinstance(entrada.get("autoUpdate"), bool):
        return entrada["autoUpdate"], "botao do /plugin"
    return False, "padrao"


def _settings_env(nome):
    """Valor de uma variavel no bloco `env` do settings que mais manda, ou None se nenhum declara."""
    for _rotulo, caminho in _arquivos_settings():
        env = (_json_ou_none(caminho) or {}).get("env")
        if isinstance(env, dict) and nome in env:
            return str(env[nome])
    return None


def _var_ligada(nome):
    """Ligada no ambiente do processo ou no `env` de um settings (vale a partir da proxima sessao)."""
    if _env_ligada(nome):
        return True
    v = _settings_env(nome)
    return v is not None and v.strip().lower() not in ("", "0", "false", "no", "off")


def _trava_update():
    """(variavel, quem) que desliga a passada de atualizacao automatica, ou (None, None).
    quem = "sessao" quando e so DISABLE_AUTOUPDATER vindo do ambiente da sessao, sem estar escrito em
    nenhum settings: e o que o app desktop faz em toda sessao (ele atualiza o proprio Claude Code), e
    ai vale oferecer FORCE_AUTOUPDATE_PLUGINS. Nao da pra distinguir do usuario que pos a variavel no
    perfil do shell, e o erro barato e perguntar a ele uma vez, nao deixar o app sem aviso nenhum.
    quem = "usuario" nas travas mais fortes ou declaradas em settings: escolha de alguem, respeitada."""
    if _var_ligada("FORCE_AUTOUPDATE_PLUGINS"):
        return None, None
    for nome in ENV_TRAVA_UPDATE:
        if not _var_ligada(nome):
            continue
        da_sessao = nome == "DISABLE_AUTOUPDATER" and _settings_env(nome) is None
        return nome, ("sessao" if da_sessao else "usuario")
    return None, None


def _ler_estado_atualizacao():
    return _json_ou_none(p_estado_atualizacao()) or {}


def _gravar_estado_atualizacao(estado):
    _gravar_atomico(p_estado_atualizacao(), json.dumps(estado, ensure_ascii=False, indent=1) + "\n")


def _cmd_python():
    """Comando pra colar: sem aspas no interpretador quando o caminho nao tem espaco, porque assim a
    mesma linha roda em sh e em PowerShell (la, linha que comeca com aspas e texto, nao comando)."""
    exe = (sys.executable or "python").replace("\\", "/")
    motor = os.path.abspath(__file__).replace("\\", "/")
    if re.search(r"\s", exe):
        exe = '"%s"' % exe
    return '%s "%s"' % (exe, motor)


def _gravar_settings(caminho, texto):
    """Grava o settings.json no arquivo de verdade (segue link simbolico em vez de troca-lo por um
    arquivo comum) e mantem a permissao que ele tinha."""
    alvo = os.path.realpath(caminho)
    pasta = os.path.dirname(alvo)
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=pasta)
    try:
        with io.open(fd, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        if os.path.exists(alvo):
            try:
                shutil.copymode(alvo, tmp)
            except OSError:
                pass
        os.replace(tmp, alvo)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _ligar_auto_update(mkt, forcar):
    """Poe `autoUpdate: true` na entrada do marketplace em settings.json do usuario e, com `forcar`,
    `FORCE_AUTOUPDATE_PLUGINS=1` no bloco `env` (no app desktop a passada de atualizacao so roda
    assim). Nao mexe no resto do arquivo. Devolve (rc, mensagem). Arquivo ilegivel = nao toca."""
    caminho = os.path.join(p_config(), "settings.json")
    texto = None
    if os.path.exists(caminho):
        try:
            with io.open(caminho, "r", encoding="utf-8-sig", newline="") as f:
                texto = f.read()
            dados = json.loads(texto) if texto.strip() else {}
        except (OSError, ValueError) as e:
            return 13, "nao consegui ler %s (%s). Nada foi alterado." % (caminho, e)
        if not isinstance(dados, dict):
            return 13, "%s nao e um objeto JSON. Nada foi alterado." % caminho
    else:
        dados = {}
    ekm = dados.get("extraKnownMarketplaces")
    if ekm is not None and not isinstance(ekm, dict):
        return 13, "`extraKnownMarketplaces` em %s nao e um objeto. Nada foi alterado." % caminho
    entrada = (ekm or {}).get(mkt)
    if entrada is not None and not isinstance(entrada, dict):
        return 13, "a entrada de `%s` em %s nao e um objeto. Nada foi alterado." % (mkt, caminho)
    env = dados.get("env")
    if forcar and env is not None and not isinstance(env, dict):
        return 13, "`env` em %s nao e um objeto. Nada foi alterado." % caminho
    if entrada is None:
        conhecidos = _json_ou_none(os.path.join(p_config(), "plugins", "known_marketplaces.json")) or {}
        fonte = conhecidos.get(mkt).get("source") if isinstance(conhecidos.get(mkt), dict) else None
        if not isinstance(fonte, dict):
            return 13, ("o marketplace `%s` nao esta cadastrado nesta maquina. Ligue pelo /plugin, "
                        "aba Marketplaces." % mkt)
        entrada = {"source": fonte}
    feito = []
    if entrada.get("autoUpdate") is not True:
        if ekm is None:
            ekm = dados["extraKnownMarketplaces"] = {}
        ekm[mkt] = entrada
        entrada["autoUpdate"] = True
        feito.append("`autoUpdate: true` no marketplace `%s`" % mkt)
    if forcar and str((env or {}).get("FORCE_AUTOUPDATE_PLUGINS", "")).strip() != "1":
        if env is None:
            env = dados["env"] = {}
        env["FORCE_AUTOUPDATE_PLUGINS"] = "1"
        feito.append("`FORCE_AUTOUPDATE_PLUGINS=1` em `env` (a sessao roda com DISABLE_AUTOUPDATER=1, como no app "
                     "desktop, e sem isso a atualizacao de plugins nao roda)")
    if not feito:
        return 0, "a atualizacao automatica de `%s` ja estava ligada em %s." % (mkt, caminho)
    recuo, fim = 2, "\n"
    if texto is not None:
        m = re.search(r'^\s*\{\s*\r?\n([ \t]+)"', texto)
        if m:
            recuo = m.group(1) if "\t" in m.group(1) else len(m.group(1))
        fim = "\r\n" if "\r\n" in texto else "\n"
    copia = caminho + ".antes-do-orquestrador"
    try:
        # allow_nan=False: um 1e400 no arquivo viraria `Infinity`, que nao e JSON
        novo = json.dumps(dados, ensure_ascii=False, indent=recuo, allow_nan=False).replace("\n", fim) + fim
        novo.encode("utf-8")
        if texto is not None:
            _gravar_atomico(copia, texto)
        _gravar_settings(caminho, novo)
    except (OSError, ValueError) as e:
        return 13, "nao consegui gravar %s (%s). Nada foi alterado." % (caminho, e)
    msg = "atualizacao automatica ligada em %s: %s." % (caminho, "; ".join(feito))
    if texto is not None:
        msg += " Copia de antes: %s." % copia
    return 0, msg


def cmd_atualizacao(args):
    if args.hook:
        try:
            return _atualizacao(args)
        except Exception:
            return 0
    return _atualizacao(args)


def _atualizacao(args):
    hook = args.hook
    if args.nao_perguntar:
        estado = _ler_estado_atualizacao()
        estado["recusou"] = True
        estado["quando_recusou"] = _agora_iso()
        _gravar_estado_atualizacao(estado)
        print("anotado: o plugin nao volta a perguntar sobre atualizacao automatica.")
        return 0
    mkt = _marketplace_da_instalacao(_raiz_plugin(args))
    if not mkt:
        if not hook:
            print("esta copia do plugin nao veio de um marketplace (pasta solta ou --plugin-dir): "
                  "nao ha atualizacao automatica pra ligar.")
        return 0 if hook else 10
    ligada, origem = _estado_auto_update(mkt)
    trava, quem = _trava_update()
    if args.ligar:
        rc, msg = _ligar_auto_update(mkt, forcar=(quem == "sessao"))
        if rc != 0:
            sys.stderr.write("erro: " + msg + "\n")
            return rc
        print(msg)
        estado = _ler_estado_atualizacao()
        estado["ligou"] = _agora_iso()
        _gravar_estado_atualizacao(estado)
        ligada, origem = _estado_auto_update(mkt)
        trava, quem = _trava_update()
        if not ligada:
            print("atencao: o settings %s desliga a atualizacao deste marketplace e manda mais que o "
                  "do usuario; ela continua desligada." % origem.replace("settings ", ""))
        if trava:
            print("atencao: a variavel %s desliga toda atualizacao automatica nesta maquina; se foi "
                  "voce que definiu e quer so a dos plugins, defina tambem FORCE_AUTOUPDATE_PLUGINS=1."
                  % trava)
        if ligada and not trava:
            print("vale a partir da proxima sessao; a versao nova chega nos primeiros minutos dela.")
        return 0
    if hook:
        if _env_ligada("ORQ_SEM_AVISO_ATUALIZACAO"):
            return 0
        if not ligada and origem != "padrao":
            return 0  # alguem desligou de proposito: nao e o plugin que vai insistir
        if trava and quem != "sessao":
            return 0  # idem: quem desligou as atualizacoes da maquina foi o usuario ou a empresa
        if ligada and not trava:
            return 0  # esta tudo certo
        estado = _ler_estado_atualizacao()
        if estado.get("recusou") or _int0(estado.get("avisos")) >= AVISO_ATUALIZACAO_MAX:
            return 0
        ultimo = _parse_ts(estado.get("ultimo_aviso")) if estado.get("ultimo_aviso") else None
        if ultimo is not None and datetime.now().astimezone() - ultimo < timedelta(days=AVISO_ATUALIZACAO_DIAS):
            return 0
        estado["ultimo_aviso"] = _agora_iso()
        estado["avisos"] = _int0(estado.get("avisos")) + 1
        _gravar_estado_atualizacao(estado)
        cmd = _cmd_python()
        if ligada:
            motivo = ("O marketplace `%s` esta com a atualizacao automatica ligada, mas esta sessao roda "
                      "com DISABLE_AUTOUPDATER=1 (o app desktop faz isso em toda sessao), o que desliga "
                      "tambem a atualizacao de plugins" % mkt)
        elif trava:
            motivo = ("O marketplace `%s` esta com a atualizacao automatica desligada (padrao do Claude "
                      "Code pra marketplace de terceiro) e esta sessao roda com DISABLE_AUTOUPDATER=1 (o app "
                      "desktop faz isso em toda sessao), o que desliga tambem a atualizacao de plugins" % mkt)
        else:
            motivo = ("O marketplace `%s` esta com a atualizacao automatica desligada (padrao do Claude "
                      "Code pra marketplace de terceiro)" % mkt)
        muda = "`autoUpdate: true` na entrada do marketplace"
        if trava:
            muda += " e `FORCE_AUTOUPDATE_PLUGINS=1` no bloco `env`"
        print("orquestrador: este plugin nao esta recebendo atualizacoes sozinho. %s; correcoes novas nao "
              "chegam. Na primeira resposta, diga isso ao usuario em 1 linha e pergunte se ele quer "
              "ligar. Se sim, rode: %s atualizacao --ligar (poe %s no settings.json do usuario e guarda "
              "copia do arquivo). Se nao, rode: %s atualizacao --nao-perguntar. Nao ligue sem a resposta "
              "dele." % (motivo, cmd, muda, cmd))
        return 0
    dados = {"marketplace": mkt, "ligada": ligada, "origem": origem, "travada_por": trava,
             "trava_de": quem}
    if args.json:
        print(json.dumps(dados, ensure_ascii=False))
    else:
        print("marketplace: %s" % mkt)
        print("atualizacao automatica: %s (%s)" % ("LIGADA" if ligada else "DESLIGADA", origem))
        if trava:
            print("mas nao roda: a variavel %s desliga a atualizacao em segundo plano (%s)"
                  % (trava, "vem do ambiente da sessao, como no app desktop" if quem == "sessao" else "escolha desta maquina"))
        if not ligada or quem == "sessao":
            print("ligar: %s atualizacao --ligar" % _cmd_python())
    return 0 if ligada and not trava else 3


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
                   help='repetivel; a classe e obrigatoria: "classe: detalhe" (classes abaixo)')
    r.add_argument("--licao")
    r.add_argument("--projeto")
    r.add_argument("--tarefa")
    r.add_argument("--experimento", action="store_true")
    r.add_argument("--achados", type=int, help="revisao: quantos achados o revisor trouxe")
    r.add_argument("--confirmados", type=int,
                   help="revisao: quantos o chefe confirmou reproduzindo ou lendo o codigo")
    r.add_argument("--tokens", type=int)
    r.add_argument("--agente", help="descricao do subagente (igual ou prefixo); deduz tipo, "
                                    "modelo real e tokens do transcript")
    r.set_defaults(fn=cmd_registrar)

    rc = sub.add_parser("reclassificar", help="conserta a classe dos erros ja gravados")
    g = rc.add_mutually_exclusive_group(required=True)
    g.add_argument("--listar", action="store_true", help="lista registros com erro de classe outro")
    g.add_argument("--id", help="id do registro a corrigir")
    rc.add_argument("--classe", action="append", choices=_NOMES_CLASSE,
                    help="repetivel; uma por erro do registro, na ordem")
    rc.set_defaults(fn=cmd_reclassificar)

    rp = sub.add_parser("reprovar", help="marca que uma entrega ja registrada foi reprovada depois "
                                         "(dono viu e nao aprovou)")
    rp.add_argument("--id", help="id do registro")
    rp.add_argument("--agente", help="descricao do despacho (campo tarefa); vale o mais recente")
    rp.add_argument("--erro", action="append",
                    help='"classe: detalhe", repetivel; ao menos um')
    rp.set_defaults(fn=cmd_reprovar)

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

    t = sub.add_parser("retomar", help="diz quais operarios a sessao despachou e quais faltam registrar")
    t.add_argument("--sessao", help="id da sessao (padrao: sessao atual)")
    t.add_argument("--desde", default="7d", help="Nh ou Nd (padrao 7d)")
    t.add_argument("--json", action="store_true")
    t.add_argument("--hook", action="store_true", help="modo silencioso para hook de sessao")
    t.set_defaults(fn=cmd_retomar)

    t = sub.add_parser("despacho", help="avalia o despacho de um operario (JSON do hook PreToolUse em stdin)")
    t.add_argument("--hook", action="store_true", help="saida JSON para hook; nunca falha")
    t.set_defaults(fn=cmd_despacho)

    u = sub.add_parser("resumo", help="1 linha com os registros da janela")
    u.add_argument("--desde", default="12h", help="Nh ou Nd (padrao 12h)")
    u.add_argument("--todas", action="store_true", help="todas as sessoes (padrao: sessao atual)")
    u.add_argument("--por-frente", action="store_true", help="1 linha por frente")
    u.set_defaults(fn=cmd_resumo)

    a = sub.add_parser("atualizar", help="grava a nota da ficha")
    a.set_defaults(fn=cmd_atualizar)

    z = sub.add_parser("atualizacao", help="diz se o plugin recebe versoes novas sozinho; --ligar liga",
                       description="Sem opcao: mostra o estado (sai 0 ligada, 3 desligada, 10 copia "
                                   "que nao veio de marketplace). So le arquivos locais, sem rede.")
    zx = z.add_mutually_exclusive_group()
    zx.add_argument("--ligar", action="store_true",
                   help="poe autoUpdate: true na entrada do marketplace no settings.json do usuario")
    zx.add_argument("--nao-perguntar", action="store_true", help="o aviso de inicio de sessao nao volta")
    z.add_argument("--json", action="store_true")
    zx.add_argument("--hook", action="store_true", help="modo silencioso para hook de sessao")
    z.add_argument("--raiz", help=argparse.SUPPRESS)
    z.set_defaults(fn=cmd_atualizacao)
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
