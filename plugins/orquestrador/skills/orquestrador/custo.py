# -*- coding: utf-8 -*-
"""custo.py - mede o consumo real de tokens dos agentes do Claude Code a partir dos transcripts.

Uso:
  python custo.py --do-registro      sessoes citadas no registro do orquestrador
  python custo.py --sessao <ID>      so uma sessao
  python custo.py                    sessao atual (env CLAUDE_CODE_SESSION_ID)
  opcoes: --json  --top N  --precos ARQUIVO  --mostrar-precos
  --precos: JSON que sobrescreve/acrescenta precos (veja --mostrar-precos); --mostrar-precos imprime a tabela e sai.

Env: ORQ_PROJECTS (padrao ~/.claude/projects), ORQ_REGISTRO (padrao ~/.claude/orquestrador/registro.jsonl),
ORQ_PRECOS (arquivo de precos, igual a --precos).
So le numeros e o campo description do meta; nao copia conversa.
"""
import argparse
import json
import os
import sys

# Precos em US$ por milhao de tokens (entrada base e saida) + multiplicador da leitura de cache sobre a entrada.
# Fonte: https://platform.claude.com/docs/en/about-claude/pricing.md (tabela linhas 17-42, notas 1 e 2; multiplicadores linhas 147-167), lida em 2026-11-16; confira os precos atuais antes de usar os numeros.
# Escrita de cache: 5 min = 1,25x a entrada, 1 h = 2x (mesma pagina, linhas 147-151).
PRECO = {
    "claude-haiku-5-5":  {"entrada": 0.10, "saida": 0.50, "leitura": 0.10, "acima_100k": {"entrada": 0.50, "saida": 2.50}},
    "claude-haiku-4-5":  {"entrada": 1.0,  "saida": 5.0,  "leitura": 0.10},
    "claude-sonnet-5-5": {"entrada": 2.0,  "saida": 10.0, "leitura": 0.05},
    "claude-sonnet-5":   {"entrada": 2.0,  "saida": 10.0, "leitura": 0.10},
    "claude-sonnet-4-6": {"entrada": 3.0,  "saida": 15.0, "leitura": 0.10},
    "claude-opus-5-5":   {"entrada": 4.0,  "saida": 20.0, "leitura": 0.05},
    "claude-opus-5":     {"entrada": 5.0,  "saida": 25.0, "leitura": 0.10},
    "claude-opus-4-8":   {"entrada": 5.0,  "saida": 25.0, "leitura": 0.10},
    "claude-fable-5-2":  {"entrada": 8.0,  "saida": 40.0, "leitura": 0.025},
    "claude-fable-5-1":  {"entrada": 10.0, "saida": 50.0, "leitura": 0.025},
    "claude-fable-5":    {"entrada": 10.0, "saida": 50.0, "leitura": 0.10},
}
PRECO_LIDO_EM = "2026-11-16"


def _num(v, minimo_exclusivo):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if v != v or v in (float("inf"), float("-inf")):   # NaN e infinito: o JSON de saida sairia invalido
        return False
    return v > 0 if minimo_exclusivo else v >= 0


def carregar_precos(caminho):
    """Le um JSON de precos. Devolve (dict_validado, None) ou (None, mensagem). Nao altera PRECO."""
    try:
        with open(caminho, "r", encoding="utf-8-sig") as fh:
            dados = json.load(fh)
    except FileNotFoundError:
        return None, "precos invalido: arquivo nao existe: %s" % caminho
    except (OSError, UnicodeDecodeError) as e:
        return None, "precos invalido: nao consegui ler %s: %s" % (caminho, e)
    except ValueError as e:
        return None, "precos invalido: nao e JSON: %s" % e
    if not isinstance(dados, dict):
        return None, "precos invalido: o topo precisa ser um objeto"
    out = {}
    for nome, v in dados.items():
        if not isinstance(nome, str) or not nome.strip():
            return None, "precos invalido: nome de modelo vazio"
        if not isinstance(v, dict):
            return None, "precos invalido: %s: valor precisa ser objeto" % nome
        extra = set(v) - {"entrada", "saida", "leitura", "acima_100k"}
        if extra:
            return None, "precos invalido: %s: chave desconhecida: %s" % (nome, ", ".join(sorted(map(str, extra))))
        if not _num(v.get("entrada"), True):
            return None, "precos invalido: %s: entrada precisa ser numero maior que zero" % nome
        if not _num(v.get("saida"), True):
            return None, "precos invalido: %s: saida precisa ser numero maior que zero" % nome
        if not _num(v.get("leitura"), False):
            return None, "precos invalido: %s: leitura obrigatoria, numero >= 0" % nome
        item = {"entrada": v["entrada"], "saida": v["saida"], "leitura": v["leitura"]}
        if "acima_100k" in v:
            f = v["acima_100k"]
            if not isinstance(f, dict) or set(f) != {"entrada", "saida"} \
                    or not _num(f.get("entrada"), True) or not _num(f.get("saida"), True):
                return None, "precos invalido: %s: acima_100k precisa de entrada e saida numericos maiores que zero" % nome
            item["acima_100k"] = {"entrada": f["entrada"], "saida": f["saida"]}
        out[nome.strip().lower()] = item
    return out, None


PADRAO_DA_FAMILIA = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5", "fable": "claude-fable-5-2"}
CHAVE_FALLBACK = "claude-sonnet-5-5"   # familia desconhecida
UNIDADE = "claude-haiku-5-5"           # custo = tokens de entrada equivalentes do Haiku 5.5 (US$ 0,10/MTok)
LIMITE_FAIXA = 100000                  # "acima_100k" vale quando o contexto da resposta passa disto
MULT_ESCRITA_5M = 1.25
MULT_ESCRITA_1H = 2.0

BS = chr(92)
PAPEIS = ["chefe", "orq-leitor", "orq-executor", "orq-designer", "orq-revisor", "orq-mestre", "orq-engenheiro",
          "general-purpose", "outros"]
NIVEIS = ["0", "1", "2", "3+"]


def _long(p):
    p = os.path.abspath(p)
    if os.name == "nt" and not p.startswith(BS + BS + "?" + BS):
        return BS + BS + "?" + BS + p
    return p


def familia(modelo):
    m = (modelo or "").lower()
    for f in ("haiku", "sonnet", "opus", "fable"):
        if f in m:
            return f
    return "outro"


def chave_preco(modelo):
    """(chave de PRECO, estimado). Maior chave que e prefixo do modelo; senao padrao da familia (estimado)."""
    m = (modelo or "").lower()
    achadas = [k for k in PRECO if m.startswith(k)]
    if achadas:
        return max(achadas, key=len), False
    fam = familia(m)
    if fam in PADRAO_DA_FAMILIA:
        return PADRAO_DA_FAMILIA[fam], True
    return CHAVE_FALLBACK, True


def custo(chave, entrada, leitura, escrita_5m, escrita_1h, saida):
    """Custo de UMA resposta em tokens de entrada equivalentes do Haiku 5.5, com as parcelas ja ponderadas."""
    p = PRECO[chave]
    ent_usd, sai_usd = p["entrada"], p["saida"]
    if "acima_100k" in p and (entrada + leitura + escrita_5m + escrita_1h) > LIMITE_FAIXA:
        ent_usd, sai_usd = p["acima_100k"]["entrada"], p["acima_100k"]["saida"]
    peso = ent_usd / PRECO[UNIDADE]["entrada"]
    r = sai_usd / ent_usd
    p_ent = peso * entrada
    p_leit = peso * p["leitura"] * leitura
    p_esc = peso * (MULT_ESCRITA_5M * escrita_5m + MULT_ESCRITA_1H * escrita_1h)
    p_saida = peso * r * saida
    total = p_ent + p_leit + p_esc + p_saida
    return {
        "custo": total,
        "custo_usd": total * PRECO[UNIDADE]["entrada"] / 1e6,
        "entrada": p_ent,
        "leitura_cache": p_leit,
        "escrita_cache": p_esc,
        "saida": p_saida,
    }


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def ler_agente(caminho_jsonl, chefe=False):
    """Le um transcript e devolve {"respostas": [...]} dedupado por message.id."""
    por_id = {}
    ordem = []
    n = 0
    with open(_long(caminho_jsonl), encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                o = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(o, dict) or o.get("type") != "assistant":
                continue
            if chefe and o.get("isSidechain") is True:
                continue
            m = o.get("message")
            if not isinstance(m, dict) or m.get("model") == "<synthetic>":
                continue
            u = m.get("usage")
            if not isinstance(u, dict) or not u:
                continue
            n += 1
            mid = m.get("id") or o.get("requestId") or "sem-id-%d" % n
            out = _int(u.get("output_tokens"))
            cw = _int(u.get("cache_creation_input_tokens"))
            cc = u.get("cache_creation")
            cw1h = 0
            if isinstance(cc, dict):
                cw1h = min(_int(cc.get("ephemeral_1h_input_tokens")), cw)
            resp = {
                "in": _int(u.get("input_tokens")),
                "cr": _int(u.get("cache_read_input_tokens")),
                "cw5": cw - cw1h,
                "cw1h": cw1h,
                "out": out,
                "model": m.get("model") or "",
            }
            if mid not in por_id:
                ordem.append(mid)
                por_id[mid] = resp
            elif out > por_id[mid]["out"]:
                por_id[mid] = resp
    return {"respostas": [por_id[i] for i in ordem]}


def _scan(d):
    try:
        return list(os.scandir(_long(d)))
    except OSError:
        return []


def _varrer(pasta, acc):
    for e in _scan(pasta):
        if e.is_dir():
            _varrer(os.path.join(pasta, e.name), acc)
        else:
            acc.append(os.path.join(pasta, e.name))


def _registro_sessoes():
    p = os.environ.get("ORQ_REGISTRO") or os.path.join(os.path.expanduser("~"), ".claude", "orquestrador", "registro.jsonl")
    vistos = []
    try:
        with open(_long(p), encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                try:
                    o = json.loads(raw)
                except ValueError:
                    continue
                s = o.get("sessao") if isinstance(o, dict) else None
                if isinstance(s, str) and s and s not in vistos:
                    vistos.append(s)
    except OSError:
        pass
    return vistos


def _ler_meta(jsonl):
    p = jsonl[:-len(".jsonl")] + ".meta.json"
    try:
        with open(_long(p), encoding="utf-8", errors="replace") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _linha(sessao, arquivo, desc, papel, nivel, resp):
    cont = {}
    for r in resp:
        cont[r["model"]] = cont.get(r["model"], 0) + 1
    modelo = max(cont, key=lambda k: cont[k]) if cont else ""
    fam = familia(modelo)
    est = False
    ent = sum(r["in"] for r in resp)
    leit = sum(r["cr"] for r in resp)
    c5 = sum(r["cw5"] for r in resp)
    c1 = sum(r["cw1h"] for r in resp)
    sai = sum(r["out"] for r in resp)
    # custo por resposta (a familia da resposta pode diferir do modelo majoritario)
    tot = {"custo": 0.0, "custo_usd": 0.0, "entrada": 0.0, "leitura_cache": 0.0, "escrita_cache": 0.0, "saida": 0.0}
    for r in resp:
        ch, e = chave_preco(r["model"])
        est = est or e
        c = custo(ch, r["in"], r["cr"], r["cw5"], r["cw1h"], r["out"])
        for k in tot:
            tot[k] += c[k]
    ctxs = [r["in"] + r["cr"] + r["cw5"] + r["cw1h"] for r in resp]
    return {
        "sessao": sessao, "arquivo": arquivo, "descricao": (desc or "")[:60], "papel": papel, "nivel": nivel,
        "modelo": modelo, "familia": fam, "estimado": est, "respostas": len(resp),
        "ctx_1a": ctxs[0], "ctx_max": max(ctxs), "entrada": ent, "leitura_cache": leit,
        "escrita_cache": c5 + c1, "escrita_cache_1h": c1, "saida": sai,
        "custo": tot["custo"], "custo_usd": tot["custo_usd"],
        "_parc": {k: tot[k] for k in ("entrada", "leitura_cache", "escrita_cache", "saida")},
        "_resp": resp,
    }


def coletar(sessoes, projects):
    agentes = []
    sem_transcript = 0
    escopos = [e.name for e in _scan(projects) if e.is_dir()]
    for sid in sessoes:
        achou = False
        vistos = set()
        for esc in escopos:
            base = os.path.join(projects, esc)
            chefe = os.path.join(base, sid + ".jsonl")
            if os.path.isfile(_long(chefe)) and (sid, sid + ".jsonl") not in vistos:
                vistos.add((sid, sid + ".jsonl"))
                achou = True
                resp = ler_agente(chefe, chefe=True)["respostas"]
                if resp:
                    agentes.append(_linha(sid, sid + ".jsonl", "chefe da sessao " + sid[:8], "chefe", 0, resp))
            sub = os.path.join(base, sid, "subagents")
            if os.path.isdir(_long(sub)):
                achou = True
                arqs = []
                _varrer(sub, arqs)
                for a in sorted(arqs):
                    nome = os.path.basename(a)
                    if not nome.startswith("agent-"):
                        continue
                    if (sid, nome) in vistos:
                        continue
                    if nome.endswith(".meta.json"):
                        if not os.path.isfile(_long(a[:-len(".meta.json")] + ".jsonl")):
                            vistos.add((sid, nome))
                            sem_transcript += 1
                        continue
                    if not nome.endswith(".jsonl"):
                        continue
                    vistos.add((sid, nome))
                    meta = _ler_meta(a)
                    resp = ler_agente(a)["respostas"]
                    if not resp:
                        continue
                    papel = "?"
                    nivel = 1
                    desc = ""
                    if meta:
                        papel = meta.get("agentType") or "?"
                        sd = meta.get("spawnDepth")
                        if isinstance(sd, int) and not isinstance(sd, bool) and sd >= 1:
                            nivel = sd
                        desc = meta.get("description") or ""
                    agentes.append(_linha(sid, nome, desc, papel, nivel, resp))
        if not achou:
            sys.stderr.write("aviso: sessao nao achada: %s\n" % sid)
    return agentes, sem_transcript


def _pct(x, tot):
    return (100.0 * x / tot) if tot else 0.0


def _bucket_papel(p):
    # agente de plugin pode aparecer com prefixo ("orquestrador:orq-leitor"): conta como o papel puro
    if isinstance(p, str) and ":" in p:
        p = p.rsplit(":", 1)[1]
    return p if p in PAPEIS and p != "outros" else "outros"


def _bucket_nivel(n):
    return str(n) if n in (0, 1, 2) else "3+"


def _media(l):
    return (sum(l) / len(l)) if l else 0.0


def _simular(agentes, fn, fator_out=1.0):
    tot = 0.0
    for a in agentes:
        for r in a["_resp"]:
            i, cr, c5, c1 = fn(r)
            tot += custo(chave_preco(r["model"])[0], i, cr, c5, c1, r["out"] * fator_out)["custo"]
    return tot


def _menos_contexto(r, n=20000):
    i, cr, c5, c1 = r["in"], r["cr"], r["cw5"], r["cw1h"]
    falta = n
    t = min(cr, falta); cr -= t; falta -= t
    t = min(c5, falta); c5 -= t; falta -= t
    t = min(c1, falta); c1 -= t; falta -= t
    t = min(i, falta); i -= t; falta -= t
    return i, cr, c5, c1


def agregar(agentes, sessoes, sem_transcript, top_n):
    total = sum(a["custo"] for a in agentes)
    res = {
        "total": {"custo": total, "custo_usd": sum(a["custo_usd"] for a in agentes),
                  "agentes": len(agentes), "respostas": sum(a["respostas"] for a in agentes)},
    }
    comp = {k: sum(a["_parc"][k] for a in agentes) for k in ("entrada", "leitura_cache", "escrita_cache", "saida")}
    res["por_componente"] = {k: {"custo": v, "pct": _pct(v, total)} for k, v in comp.items()}

    pm = {}
    for a in agentes:
        d = pm.setdefault(a["modelo"], {"agentes": 0, "respostas": 0, "custo": 0.0})
        d["agentes"] += 1; d["respostas"] += a["respostas"]; d["custo"] += a["custo"]
    for d in pm.values():
        d["pct"] = _pct(d["custo"], total)
    res["por_modelo"] = pm

    pp = {p: {"agentes": 0, "respostas": 0, "custo": 0.0, "_r": [], "_c1": [], "_cm": []} for p in PAPEIS}
    for a in agentes:
        d = pp[_bucket_papel(a["papel"])]
        d["agentes"] += 1; d["respostas"] += a["respostas"]; d["custo"] += a["custo"]
        d["_r"].append(a["respostas"]); d["_c1"].append(a["ctx_1a"]); d["_cm"].append(a["ctx_max"])
    res["por_papel"] = {}
    for p, d in pp.items():
        res["por_papel"][p] = {"agentes": d["agentes"], "respostas": d["respostas"], "custo": d["custo"],
                               "pct": _pct(d["custo"], total), "respostas_media": _media(d["_r"]),
                               "ctx_1a_media": _media(d["_c1"]), "ctx_max_media": _media(d["_cm"])}

    pn = {n: {"agentes": 0, "respostas": 0, "custo": 0.0} for n in NIVEIS}
    for a in agentes:
        d = pn[_bucket_nivel(a["nivel"])]
        d["agentes"] += 1; d["respostas"] += a["respostas"]; d["custo"] += a["custo"]
    for d in pn.values():
        d["pct"] = _pct(d["custo"], total)
    res["por_nivel"] = pn

    res["top"] = [{"descricao": a["descricao"], "papel": a["papel"], "modelo": a["modelo"],
                   "respostas": a["respostas"], "custo": a["custo"], "pct": _pct(a["custo"], total)}
                  for a in sorted(agentes, key=lambda x: -x["custo"])[:top_n]]

    s1 = _simular(agentes, lambda r: (r["in"] * 0.8, r["cr"] * 0.8, r["cw5"] * 0.8, r["cw1h"] * 0.8), 0.8)
    s2 = _simular(agentes, _menos_contexto)
    res["simulacao"] = {
        "respostas_menos_20": {"custo": s1, "economia_pct": _pct(total - s1, total)},
        "contexto_inicial_menos_20k": {"custo": s2, "economia_pct": _pct(total - s2, total)},
    }
    res["sessoes"] = list(sessoes)
    res["sem_transcript"] = sem_transcript
    res["agentes"] = [{k: v for k, v in a.items() if not k.startswith("_")} for a in agentes]
    return res


def _n(x):
    return "{:,}".format(int(round(x))).replace(",", ".")


def _p(x):
    return "%.1f%%" % x


def _tabela(titulo, cab, linhas):
    print("== " + titulo)
    larg = [len(c) for c in cab]
    for l in linhas:
        for i, c in enumerate(l):
            larg[i] = max(larg[i], len(c))
    fmt = lambda l: "  ".join(c.ljust(larg[i]) if i == 0 else c.rjust(larg[i]) for i, c in enumerate(l))
    print(fmt(cab))
    for l in linhas:
        print(fmt(l))
    print()


def _nome_fam(f):
    return f + (" (estimado)" if chave_preco(f)[1] else "")


def imprimir(res):
    t = res["total"]
    _tabela("TOTAL", ["agentes", "respostas", "custo", "US$"],
            [[_n(t["agentes"]), _n(t["respostas"]), _n(t["custo"]), "%.2f" % t["custo_usd"]]])
    _tabela("POR COMPONENTE", ["componente", "custo", "pct"],
            [[k, _n(v["custo"]), _p(v["pct"])] for k, v in res["por_componente"].items()])
    _tabela("POR MODELO", ["modelo", "agentes", "respostas", "custo", "pct"],
            [[_nome_fam(k), _n(v["agentes"]), _n(v["respostas"]), _n(v["custo"]), _p(v["pct"])]
             for k, v in res["por_modelo"].items()])
    _tabela("POR PAPEL", ["papel", "agentes", "respostas", "custo", "pct", "resp_media", "ctx_1a_med", "ctx_max_med"],
            [[k, _n(v["agentes"]), _n(v["respostas"]), _n(v["custo"]), _p(v["pct"]), _n(v["respostas_media"]),
              _n(v["ctx_1a_media"]), _n(v["ctx_max_media"])] for k, v in res["por_papel"].items()])
    _tabela("POR NIVEL", ["nivel", "agentes", "respostas", "custo", "pct"],
            [[k, _n(v["agentes"]), _n(v["respostas"]), _n(v["custo"]), _p(v["pct"])] for k, v in res["por_nivel"].items()])
    _tabela("TOP", ["descricao", "papel", "modelo", "respostas", "custo", "pct"],
            [[v["descricao"], v["papel"], v["modelo"], _n(v["respostas"]), _n(v["custo"]), _p(v["pct"])] for v in res["top"]])
    _tabela("SIMULACAO", ["cenario", "custo", "economia"],
            [[k, _n(v["custo"]), _p(v["economia_pct"])] for k, v in res["simulacao"].items()])
    print("sessoes: %d | sem_transcript: %d" % (len(res["sessoes"]), res["sem_transcript"]))
    print("custo = tokens de entrada equivalentes do Haiku 5.5 (US$ 0,10/MTok); precos de API")
    p = res.get("precos")
    if p:
        if p.get("arquivo"):
            n = len(p.get("sobrescritos") or [])
            print("precos: tabela interna lida em %s + %d %s de %s (estimativa a preco de tabela)"
                  % (p["lido_em"], n, "modelo" if n == 1 else "modelos", p["arquivo"]))
        else:
            print("precos: tabela interna lida em %s (estimativa a preco de tabela; mude com --precos)" % p["lido_em"])


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Consumo real de tokens dos agentes")
    ap.add_argument("--do-registro", action="store_true")
    ap.add_argument("--sessao")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--precos", metavar="ARQUIVO")
    ap.add_argument("--mostrar-precos", action="store_true")
    a = ap.parse_args(argv)
    if a.top < 1:
        sys.stderr.write("--top precisa ser >= 1\n")
        return 2
    caminho = a.precos or os.environ.get("ORQ_PRECOS") or None
    sobrescritos = []
    if caminho:
        novos, erro = carregar_precos(caminho)
        if erro:
            sys.stderr.write(erro + "\n")
            return 2
        PRECO.update(novos)
        sobrescritos = sorted(novos)
    if a.mostrar_precos:
        print(json.dumps(PRECO, ensure_ascii=False, indent=1, sort_keys=True))
        return 0
    if a.sessao:
        sessoes = [a.sessao]
    elif a.do_registro:
        sessoes = _registro_sessoes()
    else:
        s = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if not s:
            sys.stderr.write("sem sessao: passe --sessao ou --do-registro\n")
            return 2
        sessoes = [s]
    projects = os.environ.get("ORQ_PROJECTS") or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    agentes, sem = coletar(sessoes, projects)
    res = agregar(agentes, sessoes, sem, a.top)
    res["precos"] = {"lido_em": PRECO_LIDO_EM, "arquivo": caminho, "sobrescritos": sobrescritos}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        imprimir(res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
