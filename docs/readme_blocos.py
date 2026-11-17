#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Trechos do README que citam numeros, gerados de docs/uso-real.json.

O README traz marcadores `<!-- uso-real:NOME:inicio -->` e `<!-- uso-real:NOME:fim -->`;
`aplicar` troca so o miolo entre eles. Em portugues e em ingles. So biblioteca padrao.
"""
import html
import io
import os
import re
from decimal import Decimal, ROUND_HALF_UP

IMAGENS = ["banner", "numeros", "tipos", "custo", "ciclo", "modo-god"]
LEIAMES = {"pt": "README.md", "en": "README.en.md"}
NOMES = (["img-" + i for i in IMAGENS] +
         ["periodo", "tipos-texto", "modelos", "tipo-modelo", "custo-texto", "modo-god-texto"])

MODELOS = ["haiku", "sonnet", "opus", "fable"]
NOME_MODELO = {"haiku": "Haiku", "sonnet": "Sonnet", "opus": "Opus", "fable": "Fable"}
GRUPO_LER = ["busca", "leitura", "pesquisa-web", "revisao"]
GRUPO_CODIGO = ["edicao-logica", "front"]
NOME_TIPO = {
    "pt": {
        "revisao": "revisão", "leitura": "leitura", "edicao-logica": "edição lógica",
        "edicao-mecanica": "edição mecânica", "front": "front", "pesquisa-web": "pesquisa web",
        "coordenacao": "coordenação", "texto": "texto", "teste": "teste", "debug": "debug",
        "dados-sql": "dados e SQL", "busca": "busca", "outro": "outro",
    },
    "en": {
        "revisao": "review", "leitura": "reading", "edicao-logica": "logic edit",
        "edicao-mecanica": "mechanical edit", "front": "front end", "pesquisa-web": "web research",
        "coordenacao": "coordination", "texto": "writing", "teste": "tests", "debug": "debug",
        "dados-sql": "data and SQL", "busca": "search", "outro": "other",
    },
}
MESES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _arred(x, casas=0):
    q = Decimal(1).scaleb(-casas)
    return Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)


def pct(x, idioma="pt"):
    """>= 10 inteiro, < 10 com 1 casa (metade pra cima). Sem o sinal %."""
    v = _arred(x, 1)
    if v >= 10:
        return str(_arred(x, 0))
    s = str(v)
    return s.replace(".", ",") if idioma == "pt" else s


def mil(n, idioma="pt"):
    v = int(_arred(Decimal(str(n)) / 1000, 0))
    return "%d mil" % v if idioma == "pt" else "%dk" % v


def milhar(n, idioma="pt"):
    s = "{:,}".format(int(n))
    return s.replace(",", ".") if idioma == "pt" else s


def _data(s):
    a, m, d = s.split("-")
    return int(a), int(m), int(d)


def periodo(de, ate, idioma="pt"):
    a1, m1, d1 = _data(de)
    a2, m2, d2 = _data(ate)
    if (a1, m1, d1) == (a2, m2, d2):
        if idioma == "pt":
            return "em %02d/%02d/%d" % (d1, m1, a1)
        return "on %s %d, %d" % (MESES_EN[m1 - 1], d1, a1)
    if (a1, m1) == (a2, m2):
        if idioma == "pt":
            return "entre %d e %02d/%02d/%d" % (d1, d2, m1, a1)
        return "between %s %d and %d, %d" % (MESES_EN[m1 - 1], d1, d2, a1)
    if idioma == "pt":
        return "entre %02d/%02d/%d e %02d/%02d/%d" % (d1, m1, a1, d2, m2, a2)
    return "between %s %d, %d and %s %d, %d" % (MESES_EN[m1 - 1], d1, a1, MESES_EN[m2 - 1], d2, a2)


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def imagem(nome, alt, idioma="pt", estreito=False):
    pasta = "docs/img/" if idioma == "pt" else "docs/img/en/"
    p = pasta + nome
    fontes = []
    if estreito:
        fontes.append(("(prefers-color-scheme: dark) and (max-width: 600px)", p + "-escuro-estreito.svg"))
        fontes.append(("(prefers-color-scheme: dark)", p + "-escuro.svg"))
        fontes.append(("(max-width: 600px)", p + "-claro-estreito.svg"))
    else:
        fontes.append(("(prefers-color-scheme: dark)", p + "-escuro.svg"))
    linhas = ["<picture>"]
    for media, src in fontes:
        linhas.append('  <source media="%s" srcset="%s">' % (media, src))
    linhas.append('  <img alt="%s" src="%s-claro.svg" width="100%%">' % (_esc(alt), p))
    linhas.append("</picture>")
    return "\n".join(linhas)


def _soma(d, tipos):
    t = p = 0
    hk_t = hk_p = 0
    outras = corr = falh = 0
    for r in d["por_tipo"]:
        if r["tipo"] not in tipos:
            continue
        t += r["tarefas"]
        p += r["de_primeira"]
        corr += r.get("corrigido", 0)
        falh += r.get("falhou", 0)
        h = r.get("por_modelo", {}).get("haiku")
        if h:
            hk_p += h[0]
            hk_t += h[1]
    return dict(t=t, p=p, hk_t=hk_t, hk_p=hk_p, corr=corr, falh=falh)


def _tipos_texto(d, idioma):
    pt = idioma == "pt"
    ler = _soma(d, GRUPO_LER)
    cod = _soma(d, GRUPO_CODIGO)
    res = d["resultado"]
    rod = d["rodadas_max"]
    itens = []
    if ler["t"]:
        if pt:
            s = "- **Ler, pesquisar e revisar:** %d de %d tarefas passaram de primeira" % (ler["p"], ler["t"])
            if ler["hk_t"]:
                s += "; o Haiku recebeu %d delas e passou %d de primeira" % (ler["hk_t"], ler["hk_p"])
        else:
            s = "- **Reading, research and review:** %d of %d tasks passed on the first check" % (ler["p"], ler["t"])
            if ler["hk_t"]:
                s += "; Haiku got %d of them and passed %d first time" % (ler["hk_t"], ler["hk_p"])
        itens.append(s + ".")
    if cod["t"]:
        outras = cod["t"] - cod["p"]
        if pt:
            s = "- **Escrever código (edição lógica e front):** %d de %d passaram de primeira" % (cod["p"], cod["t"])
            if outras:
                s += "; das outras %d, %d o próprio operário corrigiu e %d o chefe terminou" % (
                    outras, cod["corr"], cod["falh"])
        else:
            s = "- **Writing code (logic edits and front end):** %d of %d passed on the first check" % (
                cod["p"], cod["t"])
            if outras:
                s += "; of the other %d, the worker itself fixed %d and the lead finished %d" % (
                    outras, cod["corr"], cod["falh"])
        itens.append(s + ".")
    falhou = res.get("falhou", 0)
    nao = d.get("tarefas", sum(res.values())) - res.get("de_primeira", 0)
    corrigido = nao - falhou  # tudo que nao e de_primeira nem falhou (corrigido, escalado)
    if nao:
        if pt:
            s = ("- **No total:** das %d que não passaram de primeira, %d o próprio operário corrigiu "
                 "em até %d rodadas e %d o chefe terminou.") % (nao, corrigido, rod, falhou)
        else:
            s = ("- **Overall:** of the %d that did not pass first time, the worker itself fixed %d "
                 "within %d correction rounds and the lead finished %d.") % (nao, corrigido, rod, falhou)
        itens.append(s)
    return "\n".join(itens)


def _modelos_presentes(d):
    return [m for m in MODELOS if m in d["por_modelo"]]


def _tabela_modelos(d, idioma):
    pt = idioma == "pt"
    if pt:
        cab = "| modelo | tarefas | de primeira | respostas por tarefa | saída por tarefa | contexto máximo |"
    else:
        cab = "| model | tasks | first try | replies per task | output per task | peak context |"
    linhas = [cab, "|---|---:|---:|---:|---:|---:|"]
    for m in _modelos_presentes(d):
        r = d["por_modelo"][m]
        pc = _arred(Decimal(100 * r["de_primeira"]) / Decimal(r["tarefas"]), 0)
        saida = mil(r["saida_mediana"], idioma) + (" tokens")
        linhas.append("| %s | %d | %d (%s%%) | %d | %s | %s |" % (
            NOME_MODELO[m], r["tarefas"], r["de_primeira"], pc, r["respostas_mediana"],
            saida, mil(r["contexto_mediano"], idioma)))
    return "\n".join(linhas)


def _tabela_tipo_modelo(d, idioma):
    ms = _modelos_presentes(d)
    cab = "| %s | %s |" % ("tipo" if idioma == "pt" else "type", " | ".join(NOME_MODELO[m] for m in ms))
    linhas = [cab, "|---|" + "---:|" * len(ms)]
    for r in d["por_tipo"]:
        celulas = []
        for m in ms:
            v = r.get("por_modelo", {}).get(m)
            celulas.append("%d / %d" % (v[0], v[1]) if v else "")
        nome = NOME_TIPO[idioma].get(r["tipo"], r["tipo"])
        linha = " | ".join(["| " + nome] + celulas) + " |"
        while "|  |" in linha:
            linha = linha.replace("|  |", "| |")
        linhas.append(linha)
    return "\n".join(linhas)


def _custo_texto(d, idioma):
    pt = idioma == "pt"
    c = d["custo"]
    papel = c.get("por_papel", {})
    pm = c["por_modelo"]
    hs = [pm[m] for m in ("haiku", "sonnet") if m in pm]
    ag_hs = sum(x["agentes"] for x in hs)
    pct_hs = sum(x["pct"] for x in hs)
    pag = 100.0 * ag_hs / c["agentes"]
    comp = c["por_componente"]
    relido = comp["leitura_cache"] + comp["escrita_cache"]
    chefes = papel.get("chefe", {}).get("agentes", 0)
    sim = c["simulacao"]

    def tem(nome):
        return nome in papel and papel[nome].get("agentes", 0) > 0

    def p(nome):
        return pct(papel[nome]["pct"], idioma)

    if pt:
        partes = []
        if tem("chefe"):
            partes.append("os %d chefes de sessão ficam com %s%%" % (chefes, p("chefe")))
        if tem("general-purpose"):
            partes.append("agentes genéricos (`general-purpose`), %s%%" % p("general-purpose"))
        if tem("orq-executor"):
            partes.append("executores `orq-executor`, %s%%" % p("orq-executor"))
        if tem("orq-revisor"):
            partes.append("revisores `orq-revisor`, %s%%" % p("orq-revisor"))
        if tem("orq-mestre"):
            partes.append("mestres `orq-mestre`, %s%%" % p("orq-mestre"))
        if tem("orq-leitor"):
            partes.append("leitores `orq-leitor`, %s%%" % p("orq-leitor"))
        if tem("outros"):
            partes.append("agentes de fora do plugin, %s%%" % p("outros"))
        conta = " (os %d chefes de sessão entram na conta)" % chefes if chefes else ""
        topo = "Medição do `custo.py` nas mesmas %d sessões, inteiras: %s agentes%s e %s respostas." % (
            c["sessoes"], milhar(c["agentes"], idioma), conta, milhar(c["respostas"], idioma))
        itens = [
            "- **Haiku e Sonnet na conta:** os %d agentes Haiku e Sonnet são %s%% dos agentes e %s%% do custo." % (
                ag_hs, pct(pag, idioma), pct(pct_hs, idioma)),
            "- **Reler ou escrever:** %s%% do custo é reler contexto a cada resposta (%s%% leitura de cache, "
            "%s%% escrita de cache); o que os modelos escrevem é %s%%." % (
                pct(relido, idioma), pct(comp["leitura_cache"], idioma),
                pct(comp["escrita_cache"], idioma), pct(comp["saida"], idioma)),
            "- **Por papel:** " + "; ".join(partes) + ".",
            "- **Simulação:** 20%% menos respostas corta %s%% do custo; encolher em 20 mil tokens o contexto "
            "inicial de cada agente corta %s%%." % (
                pct(sim["respostas_menos_20"], idioma), pct(sim["contexto_inicial_menos_20k"], idioma)),
        ]
    else:
        partes = []
        if tem("chefe"):
            partes.append("session leads take %s%%" % p("chefe"))
        if tem("general-purpose"):
            partes.append("generic agents (`general-purpose`), %s%%" % p("general-purpose"))
        if tem("orq-executor"):
            partes.append("`orq-executor` executors, %s%%" % p("orq-executor"))
        if tem("orq-revisor"):
            partes.append("`orq-revisor` reviewers, %s%%" % p("orq-revisor"))
        if tem("orq-mestre"):
            partes.append("`orq-mestre` foremen, %s%%" % p("orq-mestre"))
        if tem("orq-leitor"):
            partes.append("`orq-leitor` readers, %s%%" % p("orq-leitor"))
        if tem("outros"):
            partes.append("agents from outside the plugin, %s%%" % p("outros"))
        conta = " (the %d session leads are counted)" % chefes if chefes else ""
        topo = "Measured by `custo.py` over the same %d sessions, whole: %s agents%s and %s replies." % (
            c["sessoes"], milhar(c["agentes"], idioma), conta, milhar(c["respostas"], idioma))
        itens = [
            "- **Haiku and Sonnet on the bill:** the %d Haiku and Sonnet agents are %s%% of the agents and %s%% of the cost." % (
                ag_hs, pct(pag, idioma), pct(pct_hs, idioma)),
            "- **Rereading vs. writing:** %s%% of the cost is rereading context on every reply (%s%% cache reads, "
            "%s%% cache writes); what the models write is %s%%." % (
                pct(relido, idioma), pct(comp["leitura_cache"], idioma),
                pct(comp["escrita_cache"], idioma), pct(comp["saida"], idioma)),
            "- **By role:** " + "; ".join(partes) + ".",
            "- **Simulation:** 20%% fewer replies cuts %s%% of the cost; shrinking each agent's starting context "
            "by 20k tokens cuts %s%%." % (
                pct(sim["respostas_menos_20"], idioma), pct(sim["contexto_inicial_menos_20k"], idioma)),
        ]
    return topo + "\n\n" + "\n".join(itens)


def _modo_god(d, idioma):
    pt = idioma == "pt"
    c = d["custo"]
    a2 = c.get("por_andar", {}).get("2", {"agentes": 0, "pct": 0})
    if not a2["agentes"]:
        return ("O retrato atual ainda não tem obra em modo god." if pt
                else "The current snapshot has no god mode job yet.")
    m = c.get("por_papel", {}).get("orq-mestre")
    if pt:
        s = ("No uso real, %d dos %d agentes rodaram assim, no segundo andar (operário aberto por um mestre), "
             "e custaram %s%% do total") % (a2["agentes"], c["agentes"], pct(a2["pct"], idioma))
        if m and m["agentes"]:
            s += "; os %d mestres somaram %s%%" % (m["agentes"], pct(m["pct"], idioma))
    else:
        s = ("In real use, %d of the %d agents ran this way, on the second floor (a worker opened by a foreman), "
             "and cost %s%% of the total") % (a2["agentes"], c["agentes"], pct(a2["pct"], idioma))
        if m and m["agentes"]:
            s += "; the %d foremen added up to %s%%" % (m["agentes"], pct(m["pct"], idioma))
    return s + "."


def _periodo_texto(d, idioma):
    p = periodo(d["periodo"]["de"], d["periodo"]["ate"], idioma)
    if idioma == "pt":
        return ("Tudo abaixo saiu do registro do próprio motor e dos transcripts do Claude Code, em trabalho "
                "de verdade %s. Nada é estimativa: são contagens. O retrato agregado está em "
                "[`docs/uso-real.json`](docs/uso-real.json) e os gráficos são gerados dele por "
                "[`docs/graficos.py`](docs/graficos.py).") % p
    return ("Everything below comes from the engine's own log and from Claude Code transcripts, in real work "
            "%s. None of it is an estimate: these are counts. The aggregate snapshot is in "
            "[`docs/uso-real.json`](docs/uso-real.json) and the charts are generated from it by "
            "[`docs/graficos.py`](docs/graficos.py).") % p


def blocos(d, idioma="pt", titulos=None, estreito=False):
    titulos = titulos or {}
    out = {}
    for i in IMAGENS:
        out["img-" + i] = imagem(i, titulos.get(i, ""), idioma, estreito)
    out["periodo"] = _periodo_texto(d, idioma)
    out["tipos-texto"] = _tipos_texto(d, idioma)
    out["modelos"] = _tabela_modelos(d, idioma)
    out["tipo-modelo"] = _tabela_tipo_modelo(d, idioma)
    out["custo-texto"] = _custo_texto(d, idioma)
    out["modo-god-texto"] = _modo_god(d, idioma)
    return out


def aplicar(texto, blocos):
    """Troca o miolo entre os marcadores. Devolve (texto_novo, faltando)."""
    faltando = []
    for nome, miolo in blocos.items():
        ini = "<!-- uso-real:%s:inicio -->" % nome
        fim = "<!-- uso-real:%s:fim -->" % nome
        padrao = re.compile(r"(?ms)^(%s)\n.*?\n(%s)$" % (re.escape(ini), re.escape(fim)))
        if not padrao.search(texto):
            faltando.append(nome)
            continue
        texto = padrao.sub(lambda m: m.group(1) + "\n\n" + miolo + "\n\n" + m.group(2), texto, count=1)
    return texto, faltando


def titulos_de_arquivos(raiz, idioma="pt"):
    pasta = os.path.join(raiz, "docs", "img") if idioma == "pt" else os.path.join(raiz, "docs", "img", "en")
    out = {}
    for nome in IMAGENS:
        caminho = os.path.join(pasta, nome + "-claro.svg")
        titulo = ""
        if os.path.isfile(caminho):
            with io.open(caminho, encoding="utf-8") as f:
                m = re.search(r"<title[^>]*>(.*?)</title>", f.read(), re.S)
            if m:
                titulo = html.unescape(m.group(1)).strip()
        out[nome] = titulo
    return out


def _ler(caminho):
    with io.open(caminho, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def gerar(raiz, d, idioma="pt", estreito=False):
    texto = _ler(os.path.join(raiz, LEIAMES[idioma]))
    b = blocos(d, idioma, titulos_de_arquivos(raiz, idioma), estreito)
    return aplicar(texto, b)
