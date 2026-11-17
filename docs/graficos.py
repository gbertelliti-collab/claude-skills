#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Graficos e numeros do README a partir do uso real do orquestrador.

    python docs/graficos.py --coletar    # le o SEU registro e os transcripts e regrava docs/uso-real.json
    python docs/graficos.py              # redesenha docs/img e preenche os trechos com numero dos README
    python docs/graficos.py --conferir   # nao grava nada; sai 1 se README ou imagem nao batem com o JSON

O uso-real.json so guarda numeros agregados: nenhum nome de projeto, brief,
tarefa ou caminho sai do registro. Cada imagem sai em portugues e ingles, tema
claro e escuro, larga (840) e estreita (420, para celular). So biblioteca padrao.
"""
import argparse
import collections
import io
import json
import os
import statistics
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import readme_blocos as rb  # noqa: E402

RAIZ = os.path.dirname(AQUI)
DADOS = os.path.join(AQUI, "uso-real.json")
CUSTO_PY = os.path.join(RAIZ, "plugins", "orquestrador", "skills", "orquestrador", "custo.py")

MODELOS = ["haiku", "sonnet", "opus", "fable"]
MIN_LINHA = 4  # tipo com menos tarefas que isto entra em "outros tipos"
LARGO, ESTREITO = 840, 420

FONTE = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
TEMAS = {
    "claro": dict(fundo="#ffffff", cartao="#f6f8fa", borda="#d1d9e0", grade="#e4e8ec",
                  tinta="#1f2328", tinta2="#59636e", tinta3="#818b98", s1="#2a78d6", s2="#eb6834"),
    "escuro": dict(fundo="#0d1117", cartao="#151b23", borda="#3d444d", grade="#262c36",
                   tinta="#f0f6fc", tinta2="#9198a1", tinta3="#7d8590", s1="#3987e5", s2="#d95926"),
}

TXT = {
    "pt": dict(
        banner_olho="PLUGIN DO CLAUDE CODE",
        banner_frase=["Um chefe que pensa e confere, operários baratos", "que leem e digitam, e uma ficha que aprende",
                      "quem deve receber a próxima tarefa."],
        banner_selos=["4 skills", "5 agentes", "motor em Python puro"],
        chefe="chefe", chefe_sub="a sessão: decide e confere",
        papeis=[("leitor", "Haiku"), ("executor", "Sonnet"), ("revisor", "Sonnet")],
        ficha_faixa="ficha: 1 linha por tarefa, e a rota se ajusta",
        banner_titulo="orquestrador: plugin do Claude Code com um chefe, operários Haiku e Sonnet e uma ficha que aprende",
        n1=("tarefas delegadas", "em %d dias, %d sessões", "e %d projetos diferentes"),
        n2=("aprovadas de primeira", "%d de %d passaram na", "1ª conferência do chefe"),
        n3=("voltaram para o chefe", "outras %d fecharam em", "até %d rodadas de correção"),
        n4=("do custo em tokens", "é o que gastaram os %d", "agentes Haiku e Sonnet"),
        n_titulo="%d tarefas delegadas, %d%% aprovadas de primeira, %d voltaram para o chefe, %s%% do custo nos agentes Haiku e Sonnet",
        tipos_titulo="Resultado por tipo de tarefa", tipos_sub1="%d tarefas delegadas",
        tipos_sub2="o comprimento da barra é a quantidade de tarefas",
        tipos_leg=("passou de primeira", "precisou de correção"), de="%d de %d", outros="outros %d tipos",
        tipos_item="%s %d de %d de primeira",
        custo_titulo="Quem trabalha e quem custa", custo_sub1="%s agentes e %s respostas em %d sessões inteiras",
        custo_sub2="custo em tokens ponderado pelo preço de cada modelo",
        custo_leg=("parcela dos agentes", "parcela do custo"), agentes="%d agentes",
        custo_alt="Parcela dos agentes e parcela do custo por modelo", custo_item="%s %s%% dos agentes e %s%% do custo",
        passos=[("Ficha", "rota de cada tipo"), ("Quebrar", "tipo, dono, aceite"), ("Brief", "tudo desenhado"),
                ("Despachar", "em paralelo"), ("Conferir", "chefe roda o aceite"), ("Registrar", "1 linha por tarefa")],
        corrigir=("Corrigir", "até 3 rodadas"), nao_passou="não passou",
        volta="a ficha aprende: a próxima tarefa do tipo já sai com rota e avisos", volta_curta="a ficha aprende a rota",
        ciclo_titulo="Ciclo do chefe: ficha, quebrar, brief, despachar, conferir (se não passou, corrigir em até 3 rodadas) "
                     "e registrar; o registro volta para a ficha, que aprende",
        eng=("engenheiro · Fable", "3 visitas: planta, consulta, vistoria"),
        mestre="mestre de obras · Opus", frente="frente %s: quebra, despacha, confere",
        god_titulo="Modo god: um engenheiro em Fable faz 3 visitas; 2 mestres de obras em Opus tocam uma frente cada, "
                   "cada um com leitor Haiku, executor Sonnet e revisor Sonnet",
    ),
    "en": dict(
        banner_olho="CLAUDE CODE PLUGIN",
        banner_frase=["A lead that thinks and checks, cheap workers", "that read and type, and a scorecard that learns",
                      "who should get the next task."],
        banner_selos=["4 skills", "5 agents", "pure Python engine"],
        chefe="lead", chefe_sub="the session: decides and checks",
        papeis=[("reader", "Haiku"), ("executor", "Sonnet"), ("reviewer", "Sonnet")],
        ficha_faixa="scorecard: 1 line per task, and the route adjusts",
        banner_titulo="orquestrador: Claude Code plugin with a lead, Haiku and Sonnet workers and a scorecard that learns",
        n1=("tasks delegated", "in %d days, %d sessions", "and %d different projects"),
        n2=("passed first try", "%d of %d passed the", "lead's first check"),
        n3=("went back to the lead", "another %d closed within", "%d correction rounds"),
        n4=("of the token cost", "is what the %d Haiku", "and Sonnet agents spent"),
        n_titulo="%d tasks delegated, %d%% passed first try, %d went back to the lead, %s%% of the cost on Haiku and Sonnet agents",
        tipos_titulo="Result by task type", tipos_sub1="%d tasks delegated",
        tipos_sub2="bar length is the number of tasks",
        tipos_leg=("passed first try", "needed correction"), de="%d of %d", outros="other %d types",
        tipos_item="%s %d of %d first try",
        custo_titulo="Who works and who costs", custo_sub1="%s agents and %s replies in %d whole sessions",
        custo_sub2="token cost weighted by each model's price",
        custo_leg=("share of agents", "share of cost"), agentes="%d agents",
        custo_alt="Share of agents and share of cost by model", custo_item="%s %s%% of agents and %s%% of cost",
        passos=[("Scorecard", "route per type"), ("Split", "type, owner, check"), ("Brief", "fully drawn"),
                ("Dispatch", "in parallel"), ("Check", "lead runs the check"), ("Log", "1 line per task")],
        corrigir=("Correct", "up to 3 rounds"), nao_passou="did not pass",
        volta="the scorecard learns: the next task of the type starts with route and warnings",
        volta_curta="the scorecard learns the route",
        ciclo_titulo="Lead's cycle: scorecard, split, brief, dispatch, check (if it did not pass, correct in up to 3 rounds) "
                     "and log; the log feeds the scorecard, which learns",
        eng=("engineer · Fable", "3 visits: blueprint, consult, inspection"),
        mestre="foreman · Opus", frente="workstream %s: splits, dispatches, checks",
        god_titulo="God mode: an engineer on Fable makes 3 visits; 2 foremen on Opus each run one workstream, "
                   "each with a Haiku reader, a Sonnet executor and a Sonnet reviewer",
    ),
}


# ---------------------------------------------------------------- coleta

def _mediana(valores):
    valores = [v for v in valores if v]
    return int(statistics.median(valores)) if valores else 0


def coletar():
    registro = os.environ.get("ORQ_REGISTRO") or os.path.join(
        os.path.expanduser("~"), ".claude", "orquestrador", "registro.jsonl")
    linhas = []
    with io.open(registro, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if linha:
                r = json.loads(linha)
                if r.get("resultado") != "anulado":
                    linhas.append(r)
    if not linhas:
        sys.exit("registro vazio: " + registro)

    def primeira(g):
        return sum(1 for r in g if r["resultado"] == "de_primeira")

    dias = sorted(set(r["ts"][:10] for r in linhas))
    resultado = collections.Counter(r["resultado"] for r in linhas)
    por_modelo = {}
    for m in MODELOS:
        g = [r for r in linhas if r["modelo"] == m]
        if not g:
            continue
        v2 = [r for r in g if r.get("tokens_v") == 2]  # contagem por message.id
        por_modelo[m] = {
            "tarefas": len(g),
            "de_primeira": primeira(g),
            "saida_mediana": _mediana([r.get("tokens_saida") for r in v2]),
            "contexto_mediano": _mediana([r.get("contexto_max") for r in g]),
            "respostas_mediana": _mediana([r.get("respostas") for r in g]),
        }
    por_tipo = []
    for tipo, n in collections.Counter(r["tipo"] for r in linhas).most_common():
        g = [r for r in linhas if r["tipo"] == tipo]
        falhou = sum(1 for r in g if r["resultado"] == "falhou")
        item = {"tipo": tipo, "tarefas": n, "de_primeira": primeira(g), "por_modelo": {},
                "falhou": falhou, "corrigido": n - primeira(g) - falhou}
        for m in MODELOS:
            gm = [r for r in g if r["modelo"] == m]
            if gm:
                item["por_modelo"][m] = [primeira(gm), len(gm)]
        por_tipo.append(item)

    saida = subprocess.run([sys.executable, CUSTO_PY, "--do-registro", "--json"],
                           capture_output=True, check=True).stdout.decode("utf-8")
    c = json.loads(saida)
    fam = collections.defaultdict(lambda: {"agentes": 0, "respostas": 0, "pct": 0.0})
    for modelo, v in c["por_modelo"].items():
        nome = next((m for m in MODELOS if m in modelo), "outro")
        fam[nome]["agentes"] += v["agentes"]
        fam[nome]["respostas"] += v["respostas"]
        fam[nome]["pct"] += v["pct"]
    custo = {
        "sessoes": len(c["sessoes"]),
        "agentes": c["total"]["agentes"],
        "respostas": c["total"]["respostas"],
        "por_modelo": {k: {"agentes": v["agentes"], "respostas": v["respostas"], "pct": round(v["pct"], 2)}
                       for k, v in fam.items()},
        "por_componente": {k: round(v["pct"], 2) for k, v in c["por_componente"].items()},
        "por_papel": {k: {"agentes": v["agentes"], "respostas": v["respostas"], "pct": round(v["pct"], 2)}
                      for k, v in c["por_papel"].items()},
        "por_andar": {k: {"agentes": v["agentes"], "pct": round(v["pct"], 2)} for k, v in c["por_nivel"].items()},
        "simulacao": {k: round(v["economia_pct"], 1) for k, v in c["simulacao"].items()},
    }
    dados = {
        "periodo": {"de": dias[0], "ate": dias[-1], "dias": len(dias)},
        "tarefas": len(linhas),
        "sessoes": len(set(r["sessao"] for r in linhas)),
        "projetos": len(set(r["projeto"] for r in linhas)),
        "resultado": dict(resultado),
        "rodadas_max": max(r.get("rodadas") or 0 for r in linhas),
        "experimentos": sum(1 for r in linhas if r.get("experimento")),
        "por_modelo": por_modelo,
        "por_tipo": por_tipo,
        "custo": custo,
    }
    with io.open(DADOS, "w", encoding="utf-8", newline="\n") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("gravado:", DADOS)
    return dados


# ---------------------------------------------------------------- pecas de desenho

def br(numero, idioma, casas=1):
    s = "%.*f" % (casas, numero)
    return s.replace(".", ",") if idioma == "pt" else s


def esc(texto):
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def texto(x, y, conteudo, tam, cor, peso=400, ancora="start", extra=""):
    return '<text x="%s" y="%s" font-size="%s" fill="%s" font-weight="%s" text-anchor="%s"%s>%s</text>' % (
        x, y, tam, cor, peso, ancora, (" " + extra) if extra else "", esc(conteudo))


def svg(largura, altura, titulo, corpo, t, estreito):
    """A versao estreita leva fundo proprio: continua legivel se o tema da pagina nao bater."""
    fundo = ['<rect width="%d" height="%d" rx="12" fill="%s"/>' % (largura, altura, t["fundo"])] if estreito else []
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'role="img" aria-label="%s" font-family="%s">\n<title>%s</title>\n%s\n</svg>\n') % (
        largura, altura, largura, altura, esc(titulo).replace('"', "&quot;"), FONTE, esc(titulo),
        "\n".join(fundo + corpo))


def barra(x, y, w, h, cor, ponta=True):
    """Barra horizontal; so a ponta do dado (direita) e arredondada."""
    w = max(w, 2.0)
    r = min(4.0, w / 2.0, h / 2.0) if ponta else 0.0
    if r == 0:
        return '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s"/>' % (x, y, w, h, cor)
    return ('<path d="M%.1f %.1fh%.1fa%.1f %.1f 0 0 1 %.1f %.1fv%.1fa%.1f %.1f 0 0 1 -%.1f %.1fh-%.1fz" fill="%s"/>'
            % (x, y, w - r, r, r, r, r, h - 2 * r, r, r, r, r, w - r, cor))


def legenda(itens, x, y, t):
    out = []
    for cor, rotulo in itens:
        out.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s"/>' % (x, y - 9, cor))
        out.append(texto(x + 16, y, rotulo, 12.5, t["tinta2"]))
        x += 16 + int(len(rotulo) * 6.7) + 26
    return out


def caixa(cx, y, w, h, nome, sub, t, destaque=False, fundo=None):
    out = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="10" fill="%s" stroke="%s" stroke-width="%s"/>'
           % (cx - w / 2.0, y, w, h, fundo or t["cartao"], t["s1"] if destaque else t["borda"], 2 if destaque else 1)]
    out.append(texto(cx, y + h / 2.0 - (2 if sub else -5), nome, 14, t["tinta"], 600, "middle"))
    if sub:
        out.append(texto(cx, y + h / 2.0 + 16, sub, 11.5, t["tinta2"], 400, "middle"))
    return out


def ponta(x, y, direcao, cor):
    """Cabeca de seta com a ponta em (x, y)."""
    d = {"direita": "M%.1f %.1fl-7 -4v8z", "baixo": "M%.1f %.1fl-4 -7h8z", "cima": "M%.1f %.1fl-4 7h8z"}[direcao]
    return '<path d="%s" fill="%s"/>' % (d % (x, y), cor)


def fio(t, tracejado=False):
    return 'stroke="%s" stroke-width="1.5" fill="none"%s' % (t["tinta3"], ' stroke-dasharray="4 4"' if tracejado else "")


def halo(t):
    return 'stroke="%s" stroke-width="5" paint-order="stroke" stroke-linejoin="round"' % t["fundo"]


# ---------------------------------------------------------------- imagens

def banner(t, d, L, idioma, estreito):
    c = []
    larg, alt = (ESTREITO, 444) if estreito else (LARGO, 250)
    c.append('<rect x="0.5" y="0.5" width="%d" height="%d" rx="14" fill="%s" stroke="%s"/>' % (larg - 1, alt - 1, t["cartao"], t["borda"]))
    x0, y0 = (24, -6) if estreito else (40, 0)
    c.append('<rect x="%d" y="%d" width="10" height="10" rx="2" fill="%s"/>' % (x0, y0 + 43, t["s1"]))
    c.append(texto(x0 + 18, y0 + 53, L["banner_olho"], 12, t["tinta2"], 600, extra='letter-spacing="1.4"'))
    c.append(texto(x0 - 2, y0 + 108, "orquestrador", 42 if estreito else 46, t["tinta"], 700, extra='letter-spacing="-1"'))
    for i, linha in enumerate(L["banner_frase"]):
        c.append(texto(x0, y0 + 142 + 23 * i, linha, 15 if estreito else 16, t["tinta2"]))
    x = x0
    for rotulo in L["banner_selos"]:
        w = int(len(rotulo) * 6.9) + 24
        c.append('<rect x="%d" y="%d" width="%d" height="24" rx="12" fill="%s" stroke="%s"/>' % (x, y0 + 205, w, t["fundo"], t["borda"]))
        c.append(texto(x + w / 2.0, y0 + 221.5, rotulo, 12, t["tinta2"], 500, "middle"))
        x += w + 8
    # diagrama: chefe em cima, 3 operarios embaixo, ficha na base
    g = []
    g.append('<path d="M650 82V108M546 108H754M546 108V124M754 108V124M650 108V124" %s/>' % fio(t))
    g.append('<path d="M546 172V192M650 172V192M754 172V192" %s/>' % fio(t, True))
    g.append('<rect x="566" y="38" width="168" height="44" rx="10" fill="%s" stroke="%s" stroke-width="2"/>' % (t["fundo"], t["s1"]))
    g.append(texto(650, 57, L["chefe"], 14, t["tinta"], 700, "middle"))
    g.append(texto(650, 73, L["chefe_sub"], 11, t["tinta2"], 400, "middle"))
    for cx, (nome, modelo) in zip((546, 650, 754), L["papeis"]):
        g.append('<rect x="%d" y="124" width="92" height="48" rx="10" fill="%s" stroke="%s"/>' % (cx - 46, t["fundo"], t["borda"]))
        g.append(texto(cx, 144, nome, 13, t["tinta"], 600, "middle"))
        g.append(texto(cx, 161, modelo, 11.5, t["tinta2"], 400, "middle"))
    g.append('<rect x="500" y="192" width="300" height="30" rx="10" fill="%s" stroke="%s" stroke-dasharray="4 3"/>' % (t["fundo"], t["s1"]))
    g.append(texto(650, 211.5, L["ficha_faixa"], 11.5, t["tinta2"], 500, "middle"))
    if estreito:
        c.append('<g transform="translate(-440 206)">')
        c += g
        c.append("</g>")
    else:
        c += g
    return svg(larg, alt, L["banner_titulo"], c, t, estreito)


def numeros(t, d, L, idioma, estreito):
    res = d["resultado"]
    total = d["tarefas"]
    de1a = res.get("de_primeira", 0)
    falhou = res.get("falhou", 0)
    pm = d["custo"]["por_modelo"]
    baratos_pct = pm.get("haiku", {}).get("pct", 0) + pm.get("sonnet", {}).get("pct", 0)
    baratos_n = pm.get("haiku", {}).get("agentes", 0) + pm.get("sonnet", {}).get("agentes", 0)
    pct1a = int(100.0 * de1a / total + 0.5)
    itens = [
        (rb.milhar(total, idioma), L["n1"][0], L["n1"][1] % (d["periodo"]["dias"], d["sessoes"]), L["n1"][2] % d["projetos"]),
        ("%d%%" % pct1a, L["n2"][0], L["n2"][1] % (de1a, total), L["n2"][2]),
        (str(falhou), L["n3"][0], L["n3"][1] % (total - de1a - falhou), L["n3"][2] % d["rodadas_max"]),
        (rb.pct(baratos_pct, idioma) + "%", L["n4"][0], L["n4"][1] % baratos_n, L["n4"][2]),
    ]
    c = []
    w = 202 if estreito else 197
    for i, (numero, rotulo, sub1, sub2) in enumerate(itens):
        x, y = ((i % 2) * 218, (i // 2) * 156) if estreito else (i * 214, 0)
        c.append('<rect x="%.1f" y="%.1f" width="%d" height="139" rx="12" fill="%s" stroke="%s"/>' % (x + 0.5, y + 0.5, w - 1, t["cartao"], t["borda"]))
        c.append(texto(x + 18, y + 52, numero, 36, t["tinta"], 700, extra='letter-spacing="-0.5"'))
        c.append(texto(x + 18, y + 80, rotulo, 13.5, t["tinta"], 600))
        c.append(texto(x + 18, y + 102, sub1, 12, t["tinta2"]))
        c.append(texto(x + 18, y + 119, sub2, 12, t["tinta2"]))
    titulo = L["n_titulo"] % (total, pct1a, falhou, rb.pct(baratos_pct, idioma))
    return svg(ESTREITO if estreito else LARGO, 296 if estreito else 140, titulo, c, t, estreito)


def tipos(t, d, L, idioma, estreito):
    linhas, resto = [], [0, 0, 0]
    for item in d["por_tipo"]:
        if item["tarefas"] >= MIN_LINHA and item["tipo"] != "outro":
            linhas.append((rb.NOME_TIPO[idioma].get(item["tipo"], item["tipo"]), item["tarefas"], item["de_primeira"]))
        else:
            resto = [resto[0] + item["tarefas"], resto[1] + item["de_primeira"], resto[2] + 1]
    if resto[0]:
        linhas.append((L["outros"] % resto[2], resto[0], resto[1]))
    maior = max([n for _, n, _ in linhas] or [1])
    x0, larg, m = (118, 210, 8) if estreito else (150, 560, 0)
    passo, alt = 30, 16
    escala = larg / float(maior)
    c = [texto(m, 24, L["tipos_titulo"], 16, t["tinta"], 700)]
    if estreito:
        c.append(texto(m, 45, L["tipos_sub1"] % d["tarefas"], 13, t["tinta2"]))
        c.append(texto(m, 63, L["tipos_sub2"], 13, t["tinta2"]))
        yl = 90
    else:
        c.append(texto(m, 45, (L["tipos_sub1"] % d["tarefas"]) + " · " + L["tipos_sub2"], 13, t["tinta2"]))
        yl = 72
    c += legenda([(t["s1"], L["tipos_leg"][0]), (t["s2"], L["tipos_leg"][1])], m, yl, t)
    y = yl + 28
    c.append('<path d="M%d %dV%d" stroke="%s" stroke-width="1"/>' % (x0 - 1, y - 12, y + passo * len(linhas) - 8, t["borda"]))
    for nome, n, ok in linhas:
        c.append(texto(x0 - 12, y + 12.5, nome, 13, t["tinta"], 400, "end"))
        w1, w2 = ok * escala, (n - ok) * escala
        x = x0
        if ok:
            c.append(barra(x, y, w1 - (2 if n > ok else 0), alt, t["s1"], ponta=(n == ok)))
            x += w1
        if n > ok:
            c.append(barra(x, y, w2, alt, t["s2"]))
            x += w2
        c.append(texto(x + 10, y + 12.5, L["de"] % (ok, n), 12.5, t["tinta2"]))
        y += passo
    titulo = L["tipos_titulo"] + ": " + "; ".join(L["tipos_item"] % (a, k, n) for a, n, k in linhas)
    return svg(ESTREITO if estreito else LARGO, y + (4 if estreito else 0), titulo, c, t, estreito)


def custo(t, d, L, idioma, estreito):
    cu = d["custo"]
    ordem = sorted(cu["por_modelo"].items(), key=lambda kv: -kv[1]["pct"])
    x0, larg, m = (100, 250, 8) if estreito else (150, 600, 0)
    teto = 80.0
    escala = larg / teto
    c = [texto(m, 24, L["custo_titulo"], 16, t["tinta"], 700)]
    sub1 = L["custo_sub1"] % (rb.milhar(cu["agentes"], idioma), rb.milhar(cu["respostas"], idioma), cu["sessoes"])
    if estreito:
        c.append(texto(m, 45, sub1, 13, t["tinta2"]))
        c.append(texto(m, 63, L["custo_sub2"], 13, t["tinta2"]))
        yl = 90
    else:
        c.append(texto(m, 45, sub1 + " · " + L["custo_sub2"], 13, t["tinta2"]))
        yl = 72
    c += legenda([(t["s1"], L["custo_leg"][0]), (t["s2"], L["custo_leg"][1])], m, yl, t)
    y = yl + 28
    fim = y + len(ordem) * 52 - 12
    for marca in (20, 40, 60, 80):
        gx = x0 + marca * escala
        c.append('<path d="M%.1f %dV%d" stroke="%s" stroke-width="1"/>' % (gx, y - 12, fim, t["grade"]))
        c.append(texto(gx, fim + 17, "%d%%" % marca, 11.5, t["tinta3"], 400, "middle"))
    c.append('<path d="M%d %dV%d" stroke="%s" stroke-width="1"/>' % (x0 - 1, y - 12, fim, t["borda"]))
    partes = []
    for nome, v in ordem:
        ag = 100.0 * v["agentes"] / cu["agentes"]
        c.append(texto(x0 - 12, y + 13, nome.capitalize(), 13.5, t["tinta"], 600, "end"))
        c.append(texto(x0 - 12, y + 29, L["agentes"] % v["agentes"], 11.5, t["tinta3"], 400, "end"))
        c.append(barra(x0, y, ag * escala, 16, t["s1"]))
        c.append(texto(x0 + max(ag * escala, 2) + 8, y + 12.5, br(ag, idioma) + "%", 12.5, t["tinta2"], extra=halo(t)))
        c.append(barra(x0, y + 18, v["pct"] * escala, 16, t["s2"]))
        c.append(texto(x0 + max(v["pct"] * escala, 2) + 8, y + 30.5, br(v["pct"], idioma) + "%", 12.5, t["tinta2"], extra=halo(t)))
        partes.append(L["custo_item"] % (nome.capitalize(), br(ag, idioma), br(v["pct"], idioma)))
        y += 52
    return svg(ESTREITO if estreito else LARGO, fim + 28, L["custo_alt"] + ": " + "; ".join(partes), c, t, estreito)


def ciclo(t, d, L, idioma, estreito):
    passos = L["passos"]
    h = 62.0
    c = []
    if estreito:
        w, centros = 116.0, [84.0, 220.0, 356.0]
        pos = [(centros[i % 3], 8.0 if i < 3 else 118.0) for i in range(6)]
    else:
        w = 124.0
        pos = [(w / 2.0 + i * (w + 19.2), 8.0) for i in range(6)]
    for i, (nome, sub) in enumerate(passos):
        cx, y = pos[i]
        c += caixa(cx, y, w, h, nome, sub, t, destaque=(i == 4))
        if i and pos[i - 1][1] == y:  # seta na mesma linha
            x_ini = pos[i - 1][0] + w / 2.0
            c.append('<path d="M%.1f %.1fH%.1f" %s/>' % (x_ini + 2, y + h / 2.0, cx - w / 2.0 - 7, fio(t)))
            c.append(ponta(cx - w / 2.0 - 1, y + h / 2.0, "direita", t["tinta3"]))
    if estreito:  # do fim da 1a linha para o comeco da 2a
        c.append('<path d="M%.1f 72V94H%.1fV110" %s/>' % (pos[2][0], pos[3][0], fio(t)))
        c.append(ponta(pos[3][0], 117, "baixo", t["tinta3"]))
    cc, yc = pos[4]
    yk = yc + h + 42  # caixa Corrigir
    c += caixa(cc, yk, w, 46, L["corrigir"][0], L["corrigir"][1], t)
    c.append('<path d="M%.1f %.1fV%.1f" %s/>' % (cc - 30, yc + h + 2, yk - 8, fio(t)))
    c.append(ponta(cc - 30, yk - 1, "baixo", t["tinta3"]))
    c.append('<path d="M%.1f %.1fV%.1f" %s/>' % (cc + 30, yk - 2, yc + h + 8, fio(t)))
    c.append(ponta(cc + 30, yc + h + 1, "cima", t["tinta3"]))
    c.append(texto(cc - 38, yc + h + 26, L["nao_passou"], 11, t["tinta2"], 400, "end"))
    cr, yr = pos[5]
    cf, yf = pos[0]
    yb = yk + 46 + 28
    if estreito:  # volta pela margem esquerda ate o lado da Ficha
        c.append('<path d="M%.1f %.1fV%.1fH10V%.1fH%.1f" %s/>' % (cr, yr + h + 2, yb, yf + h / 2.0, cf - w / 2.0 - 8, fio(t, True)))
        c.append(ponta(cf - w / 2.0 - 1, yf + h / 2.0, "direita", t["tinta3"]))
        c.append(texto(170, yb + 4, L["volta_curta"], 12, t["tinta2"], 500, "middle", halo(t)))
    else:
        c.append('<path d="M%.1f %.1fV%.1fH%.1fV%.1f" %s/>' % (cr, yr + h + 2, yb, cf, yf + h + 8, fio(t, True)))
        c.append(ponta(cf, yf + h + 1, "cima", t["tinta3"]))
        c.append(texto(250, yb + 4, L["volta"], 12, t["tinta2"], 500, "middle", halo(t)))
    return svg(ESTREITO if estreito else LARGO, int(yb + 14), L["ciclo_titulo"], c, t, estreito)


def modo_god(t, d, L, idioma, estreito):
    c = []
    if estreito:
        centro = 210
        c.append('<path d="M%d 70V104" %s/>' % (centro, fio(t, True)))
        c.append('<path d="M60 39H4V327H73" %s/>' % fio(t, True))
        c.append(ponta(79, 327, "direita", t["tinta3"]))
        c += caixa(centro, 8, 300, 62, L["eng"][0], L["eng"][1], t, destaque=True)
        mestres = [(centro, 104, "A"), (centro, 296, "B")]
        alt = 460
    else:
        c.append('<path d="M420 70V92M210 92H630M210 92V112M630 92V112" %s/>' % fio(t, True))
        c += caixa(420, 8, 300, 62, L["eng"][0], L["eng"][1], t, destaque=True)
        mestres = [(210, 112, "A"), (630, 112, "B")]
        alt = 278
    for cm, ym, letra in mestres:
        yo = ym + 62 + (34 if estreito else 40)
        c.append('<path d="M%d %dV%dM%d %dH%dM%d %dV%dM%d %dV%dM%d %dV%d" %s/>' % (
            cm, ym + 62, yo - 18, cm - 138, yo - 18, cm + 138, cm - 138, yo - 18, yo, cm, yo - 18, yo, cm + 138, yo - 18, yo, fio(t)))
        c += caixa(cm, ym, 260 if estreito else 230, 62, L["mestre"], L["frente"] % letra, t)
        for dx, (nome, modelo) in zip((-138, 0, 138), L["papeis"]):
            c += caixa(cm + dx, yo, 124, 56, nome, modelo, t)
    return svg(ESTREITO if estreito else LARGO, alt, L["god_titulo"], c, t, estreito)


DESENHOS = [("banner", banner), ("numeros", numeros), ("tipos", tipos), ("custo", custo),
            ("ciclo", ciclo), ("modo-god", modo_god)]
assert [n for n, _ in DESENHOS] == rb.IMAGENS


# ---------------------------------------------------------------- gravar e conferir

def gerar_imagens(d):
    """Caminho relativo a raiz do repo (com /) -> conteudo do SVG."""
    out = collections.OrderedDict()
    for idioma in ("pt", "en"):
        pasta = "docs/img/" if idioma == "pt" else "docs/img/en/"
        for nome_tema, t in TEMAS.items():
            for nome, funcao in DESENHOS:
                for estreito in (False, True):
                    caminho = "%s%s-%s%s.svg" % (pasta, nome, nome_tema, "-estreito" if estreito else "")
                    out[caminho] = funcao(t, d, TXT[idioma], idioma, estreito)
    return out


def _ler(caminho):
    with io.open(caminho, encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n")


def _gravar(caminho, conteudo):
    pasta = os.path.dirname(caminho)
    if not os.path.isdir(pasta):
        os.makedirs(pasta)
    with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo)


def _svgs_em_disco():
    achados = []
    for base, _, arquivos in os.walk(os.path.join(AQUI, "img")):
        for a in arquivos:
            if a.endswith(".svg"):
                achados.append(os.path.relpath(os.path.join(base, a), RAIZ).replace(os.sep, "/"))
    return achados


def desenhar(d):
    imagens = gerar_imagens(d)
    for rel, conteudo in imagens.items():
        _gravar(os.path.join(RAIZ, rel), conteudo)
    for rel in _svgs_em_disco():
        if rel not in imagens:  # sobra de um layout antigo
            os.remove(os.path.join(RAIZ, rel))
    print("imagens: %d gravadas em docs/img" % len(imagens))
    problema = False
    for idioma, nome in rb.LEIAMES.items():
        caminho = os.path.join(RAIZ, nome)
        if not os.path.isfile(caminho):
            continue
        novo, faltando = rb.gerar(RAIZ, d, idioma, estreito=True)
        if faltando:
            print("ERRO: %s sem os marcadores de: %s" % (nome, ", ".join(faltando)))
            problema = True
            continue
        _gravar(caminho, novo)
        print("%s: %d trechos em dia" % (nome, len(rb.NOMES)))
    return 2 if problema else 0


def conferir(d):
    """Lista do que nao bate com o JSON; nao grava nada."""
    fora = []
    imagens = gerar_imagens(d)
    for rel, conteudo in imagens.items():
        caminho = os.path.join(RAIZ, rel)
        if not os.path.isfile(caminho):
            fora.append("falta a imagem " + rel)
        elif _ler(caminho) != conteudo:
            fora.append("imagem desatualizada: " + rel)
    for rel in _svgs_em_disco():
        if rel not in imagens:
            fora.append("imagem sobrando: " + rel)
    for idioma, nome in rb.LEIAMES.items():
        caminho = os.path.join(RAIZ, nome)
        if not os.path.isfile(caminho):
            fora.append("falta o arquivo " + nome)
            continue
        novo, faltando = rb.gerar(RAIZ, d, idioma, estreito=True)
        if faltando:
            fora.append("%s sem os marcadores de: %s" % (nome, ", ".join(faltando)))
        elif _ler(caminho) != novo:
            fora.append("%s com trecho de numero diferente do JSON" % nome)
    return fora


def main():
    ap = argparse.ArgumentParser(description="Graficos e numeros do README a partir do uso real")
    grupo = ap.add_mutually_exclusive_group()
    grupo.add_argument("--coletar", action="store_true", help="relê o registro e os transcripts antes de desenhar")
    grupo.add_argument("--conferir", action="store_true", help="só confere README e imagens contra o JSON (sai 1 se não batem)")
    args = ap.parse_args()
    if args.coletar:
        dados = coletar()
    else:
        with io.open(DADOS, encoding="utf-8") as f:
            dados = json.load(f)
    if args.conferir:
        fora = conferir(dados)
        for linha in fora:
            print("NAO BATE:", linha)
        if fora:
            print("rode: python docs/graficos.py")
            return 1
        print("ok: README e %d imagens batem com docs/uso-real.json" % len(gerar_imagens(dados)))
        return 0
    return desenhar(dados)


if __name__ == "__main__":
    sys.exit(main())
