#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Graficos do README a partir do uso real do orquestrador.

    python docs/graficos.py --coletar   # le o SEU registro e os transcripts e regrava docs/uso-real.json
    python docs/graficos.py             # desenha docs/img/*.svg a partir de docs/uso-real.json

O uso-real.json so guarda numeros agregados: nenhum nome de projeto, brief,
tarefa ou caminho sai do registro. So biblioteca padrao.
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
DADOS = os.path.join(AQUI, "uso-real.json")
IMG = os.path.join(AQUI, "img")
CUSTO_PY = os.path.join(AQUI, "..", "plugins", "orquestrador", "skills", "orquestrador", "custo.py")

MODELOS = ["haiku", "sonnet", "opus", "fable"]
NOME_TIPO = {
    "revisao": "revisão", "leitura": "leitura", "edicao-logica": "edição lógica",
    "edicao-mecanica": "edição mecânica", "front": "front", "pesquisa-web": "pesquisa web",
    "coordenacao": "coordenação", "texto": "texto", "teste": "teste", "debug": "debug",
    "dados-sql": "dados e SQL", "busca": "busca", "outro": "outro",
}
MIN_LINHA = 4  # tipo com menos tarefas que isto entra em "outros tipos"

FONTE = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"
TEMAS = {
    "claro": dict(fundo="#ffffff", cartao="#f6f8fa", borda="#d1d9e0", grade="#e4e8ec",
                  tinta="#1f2328", tinta2="#59636e", tinta3="#818b98", s1="#2a78d6", s2="#eb6834"),
    "escuro": dict(fundo="#0d1117", cartao="#151b23", borda="#3d444d", grade="#262c36",
                   tinta="#f0f6fc", tinta2="#9198a1", tinta3="#7d8590", s1="#3987e5", s2="#d95926"),
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
            "de_primeira": sum(1 for r in g if r["resultado"] == "de_primeira"),
            "saida_mediana": _mediana([r.get("tokens_saida") for r in v2]),
            "contexto_mediano": _mediana([r.get("contexto_max") for r in g]),
            "respostas_mediana": _mediana([r.get("respostas") for r in g]),
        }
    por_tipo = []
    for tipo, n in collections.Counter(r["tipo"] for r in linhas).most_common():
        g = [r for r in linhas if r["tipo"] == tipo]
        item = {"tipo": tipo, "tarefas": n,
                "de_primeira": sum(1 for r in g if r["resultado"] == "de_primeira"), "por_modelo": {}}
        for m in MODELOS:
            gm = [r for r in g if r["modelo"] == m]
            if gm:
                item["por_modelo"][m] = [sum(1 for r in gm if r["resultado"] == "de_primeira"), len(gm)]
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


# ---------------------------------------------------------------- desenho

def br(numero, casas=1):
    return ("%.*f" % (casas, numero)).replace(".", ",")


def milhar(n):
    return ("{:,}".format(int(n))).replace(",", ".")


def esc(texto):
    return str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def texto(x, y, conteudo, tam, cor, peso=400, ancora="start", extra=""):
    return '<text x="%s" y="%s" font-size="%s" fill="%s" font-weight="%s" text-anchor="%s"%s>%s</text>' % (
        x, y, tam, cor, peso, ancora, (" " + extra) if extra else "", esc(conteudo))


def svg(largura, altura, titulo, corpo):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" '
            'role="img" aria-label="%s" font-family="%s">\n<title>%s</title>\n%s\n</svg>\n') % (
        largura, altura, largura, altura, esc(titulo), FONTE, esc(titulo), "\n".join(corpo))


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


def banner(t):
    c = []
    c.append('<rect x="0.5" y="0.5" width="839" height="249" rx="14" fill="%s" stroke="%s"/>' % (t["cartao"], t["borda"]))
    c.append('<rect x="40" y="43" width="10" height="10" rx="2" fill="%s"/>' % t["s1"])
    c.append(texto(58, 53, "PLUGIN DO CLAUDE CODE", 12, t["tinta2"], 600, extra='letter-spacing="1.4"'))
    c.append(texto(38, 108, "orquestrador", 46, t["tinta"], 700, extra='letter-spacing="-1"'))
    c.append(texto(40, 142, "Um chefe que pensa e confere, operários baratos", 16, t["tinta2"]))
    c.append(texto(40, 165, "que leem e digitam, e uma ficha que aprende", 16, t["tinta2"]))
    c.append(texto(40, 188, "quem deve receber a próxima tarefa.", 16, t["tinta2"]))
    x = 40
    for rotulo in ("4 skills", "5 agentes", "motor em Python puro"):
        w = int(len(rotulo) * 6.9) + 24
        c.append('<rect x="%d" y="205" width="%d" height="24" rx="12" fill="%s" stroke="%s"/>' % (x, w, t["fundo"], t["borda"]))
        c.append(texto(x + w / 2.0, 221.5, rotulo, 12, t["tinta2"], 500, "middle"))
        x += w + 8
    # diagrama: chefe em cima, 3 operarios embaixo, ficha na base
    fio = 'stroke="%s" stroke-width="1.5" fill="none"' % t["tinta3"]
    c.append('<path d="M650 82V108M546 108H754M546 108V124M754 108V124M650 108V124" %s/>' % fio)
    c.append('<path d="M546 172V192M650 172V192M754 172V192" %s stroke-dasharray="3 3"/>' % fio)
    c.append('<rect x="566" y="38" width="168" height="44" rx="10" fill="%s" stroke="%s" stroke-width="2"/>' % (t["fundo"], t["s1"]))
    c.append(texto(650, 57, "chefe", 14, t["tinta"], 700, "middle"))
    c.append(texto(650, 73, "a sessão: decide e confere", 11, t["tinta2"], 400, "middle"))
    for cx, nome, modelo in ((546, "leitor", "Haiku"), (650, "executor", "Sonnet"), (754, "revisor", "Sonnet")):
        c.append('<rect x="%d" y="124" width="92" height="48" rx="10" fill="%s" stroke="%s"/>' % (cx - 46, t["fundo"], t["borda"]))
        c.append(texto(cx, 144, nome, 13, t["tinta"], 600, "middle"))
        c.append(texto(cx, 161, modelo, 11.5, t["tinta2"], 400, "middle"))
    c.append('<rect x="500" y="192" width="300" height="30" rx="10" fill="%s" stroke="%s" stroke-dasharray="4 3"/>' % (t["fundo"], t["s1"]))
    c.append(texto(650, 211.5, "ficha: 1 linha por tarefa, e a rota se ajusta", 11.5, t["tinta2"], 500, "middle"))
    return svg(840, 250, "orquestrador: plugin do Claude Code com um chefe, operários Haiku e Sonnet e uma ficha que aprende", c)


def blocos(t, d):
    res = d["resultado"]
    total = d["tarefas"]
    de1a = res.get("de_primeira", 0)
    falhou = res.get("falhou", 0)
    ajustadas = total - de1a - falhou
    pm = d["custo"]["por_modelo"]
    baratos_pct = pm.get("haiku", {}).get("pct", 0) + pm.get("sonnet", {}).get("pct", 0)
    baratos_n = pm.get("haiku", {}).get("agentes", 0) + pm.get("sonnet", {}).get("agentes", 0)
    itens = [
        (milhar(total), "tarefas delegadas",
         ["em %d dias, %d sessões" % (d["periodo"]["dias"], d["sessoes"]), "e %d projetos diferentes" % d["projetos"]]),
        ("%d%%" % round(100.0 * de1a / total), "aprovadas de primeira",
         ["%d de %d passaram na" % (de1a, total), "1ª conferência do chefe"]),
        (str(falhou), "voltaram para o chefe",
         ["outras %d fecharam em" % ajustadas, "até %d rodadas de correção" % d["rodadas_max"]]),
        (br(baratos_pct) + "%", "do custo em tokens",
         ["é o que gastaram os %d" % baratos_n, "agentes Haiku e Sonnet"]),
    ]
    c = []
    for i, (numero, rotulo, sub) in enumerate(itens):
        x = i * 214
        c.append('<rect x="%.1f" y="0.5" width="197" height="139" rx="12" fill="%s" stroke="%s"/>' % (x + 0.5, t["cartao"], t["borda"]))
        c.append(texto(x + 18, 52, numero, 36, t["tinta"], 700, extra='letter-spacing="-0.5"'))
        c.append(texto(x + 18, 80, rotulo, 13.5, t["tinta"], 600))
        c.append(texto(x + 18, 102, sub[0], 12, t["tinta2"]))
        c.append(texto(x + 18, 119, sub[1], 12, t["tinta2"]))
    return svg(840, 140, "%d tarefas delegadas, %d%% aprovadas de primeira, %d voltaram para o chefe, %s%% do custo nos agentes Haiku e Sonnet"
               % (total, round(100.0 * de1a / total), falhou, br(baratos_pct)), c)


def grafico_tipos(t, d):
    linhas, resto = [], [0, 0, 0]
    for item in d["por_tipo"]:
        if item["tarefas"] >= MIN_LINHA and item["tipo"] != "outro":
            linhas.append((NOME_TIPO.get(item["tipo"], item["tipo"]), item["tarefas"], item["de_primeira"]))
        else:
            resto = [resto[0] + item["tarefas"], resto[1] + item["de_primeira"], resto[2] + 1]
    if resto[0]:
        linhas.append(("outros %d tipos" % resto[2], resto[0], resto[1]))
    maior = max(n for _, n, _ in linhas)
    x0, larg, passo, alt = 150, 560, 30, 16
    escala = larg / float(maior)
    y = 96
    c = [texto(0, 20, "Resultado por tipo de tarefa", 16, t["tinta"], 700),
         texto(0, 41, "%d tarefas delegadas · o comprimento da barra é a quantidade de tarefas" % d["tarefas"], 13, t["tinta2"])]
    c += legenda([(t["s1"], "passou de primeira"), (t["s2"], "precisou de correção")], 0, 68, t)
    c.append('<path d="M%d 84V%d" stroke="%s" stroke-width="1"/>' % (x0 - 1, y + passo * len(linhas) - 8, t["borda"]))
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
        c.append(texto(x + 10, y + 12.5, "%d de %d" % (ok, n), 12.5, t["tinta2"]))
        y += passo
    return svg(840, y, "Resultado por tipo de tarefa: " + "; ".join("%s %d de %d de primeira" % (a, k, n) for a, n, k in linhas), c)


def grafico_custo(t, d):
    cu = d["custo"]
    ordem = sorted(cu["por_modelo"].items(), key=lambda kv: -kv[1]["pct"])
    x0, larg, teto = 150, 600, 80.0
    halo = 'stroke="%s" stroke-width="4" paint-order="stroke" stroke-linejoin="round"' % t["fundo"]
    escala = larg / teto
    y = 96
    fim = y + len(ordem) * 52 - 12
    c = [texto(0, 20, "Quem trabalha e quem custa", 16, t["tinta"], 700),
         texto(0, 41, "%s agentes e %s respostas em %d sessões inteiras · custo em tokens ponderado pelo preço de cada modelo"
               % (milhar(cu["agentes"]), milhar(cu["respostas"]), cu["sessoes"]), 13, t["tinta2"])]
    c += legenda([(t["s1"], "parcela dos agentes"), (t["s2"], "parcela do custo")], 0, 68, t)
    for marca in (20, 40, 60, 80):
        gx = x0 + marca * escala
        c.append('<path d="M%.1f 84V%d" stroke="%s" stroke-width="1"/>' % (gx, fim, t["grade"]))
        c.append(texto(gx, fim + 17, "%d%%" % marca, 11.5, t["tinta3"], 400, "middle"))
    c.append('<path d="M%d 84V%d" stroke="%s" stroke-width="1"/>' % (x0 - 1, fim, t["borda"]))
    for nome, v in ordem:
        ag = 100.0 * v["agentes"] / cu["agentes"]
        c.append(texto(x0 - 12, y + 13, nome.capitalize(), 13.5, t["tinta"], 600, "end"))
        c.append(texto(x0 - 12, y + 29, "%d agentes" % v["agentes"], 11.5, t["tinta3"], 400, "end"))
        c.append(barra(x0, y, ag * escala, 16, t["s1"]))
        c.append(texto(x0 + max(ag * escala, 2) + 8, y + 12.5, br(ag) + "%", 12.5, t["tinta2"], extra=halo))
        c.append(barra(x0, y + 18, v["pct"] * escala, 16, t["s2"]))
        c.append(texto(x0 + max(v["pct"] * escala, 2) + 8, y + 30.5, br(v["pct"]) + "%", 12.5, t["tinta2"], extra=halo))
        y += 52
    return svg(840, fim + 26, "Parcela dos agentes e parcela do custo por modelo: " + "; ".join(
        "%s %s%% dos agentes e %s%% do custo" % (k, br(100.0 * v["agentes"] / cu["agentes"]), br(v["pct"])) for k, v in ordem), c)


def caixa(cx, y, w, h, nome, sub, t, destaque=False):
    out = ['<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="10" fill="%s" stroke="%s" stroke-width="%s"/>'
           % (cx - w / 2.0, y, w, h, t["cartao"], t["s1"] if destaque else t["borda"], 2 if destaque else 1)]
    out.append(texto(cx, y + h / 2.0 - (2 if sub else -5), nome, 14, t["tinta"], 600, "middle"))
    if sub:
        out.append(texto(cx, y + h / 2.0 + 16, sub, 11.5, t["tinta2"], 400, "middle"))
    return out


def ponta(x, y, direcao, cor):
    """Cabeca de seta com a ponta em (x, y)."""
    d = {"direita": "M%.1f %.1fl-7 -4v8z", "baixo": "M%.1f %.1fl-4 -7h8z", "cima": "M%.1f %.1fl-4 7h8z"}[direcao]
    return '<path d="%s" fill="%s"/>' % (d % (x, y), cor)


def ciclo(t):
    passos = [("Ficha", "rota de cada tipo"), ("Quebrar", "tipo, dono, aceite"), ("Brief", "tudo desenhado"),
              ("Despachar", "em paralelo"), ("Conferir", "chefe roda o aceite"), ("Registrar", "1 linha por tarefa")]
    w, vao, y, h = 124.0, 19.2, 8.0, 62.0
    fio = 'stroke="%s" stroke-width="1.5" fill="none"' % t["tinta3"]
    halo = 'stroke="%s" stroke-width="5" paint-order="stroke" stroke-linejoin="round"' % t["fundo"]
    c, centros = [], []
    for i, (nome, sub) in enumerate(passos):
        cx = w / 2.0 + i * (w + vao)
        centros.append(cx)
        c += caixa(cx, y, w, h, nome, sub, t, destaque=(nome == "Conferir"))
        if i:
            x0 = cx - w / 2.0 - vao
            c.append('<path d="M%.1f %.1fH%.1f" %s/>' % (x0 + 2, y + h / 2.0, x0 + vao - 7, fio))
            c.append(ponta(x0 + vao - 1, y + h / 2.0, "direita", t["tinta3"]))
    # volta da correcao, embaixo de Conferir
    cc = centros[4]
    c += caixa(cc, 112, w, 46, "Corrigir", "até 3 rodadas", t)
    c.append('<path d="M%.1f %.1fV%.1f" %s/>' % (cc - 30, y + h + 2, 112 - 8, fio))
    c.append(ponta(cc - 30, 112 - 1, "baixo", t["tinta3"]))
    c.append('<path d="M%.1f %.1fV%.1f" %s/>' % (cc + 30, 112 - 2, y + h + 8, fio))
    c.append(ponta(cc + 30, y + h + 1, "cima", t["tinta3"]))
    c.append(texto(cc - 38, 96, "não passou", 11, t["tinta2"], 400, "end"))
    # a ficha aprende: de Registrar de volta para Ficha
    cr, cf, yb = centros[5], centros[0], 186.0
    c.append('<path d="M%.1f %.1fV%.1fH%.1fV%.1f" %s stroke-dasharray="4 4"/>' % (cr, y + h + 2, yb, cf, y + h + 8, fio))
    c.append(ponta(cf, y + h + 1, "cima", t["tinta3"]))
    c.append(texto(250, yb + 4, "a ficha aprende: a próxima tarefa do tipo já sai com rota e avisos", 12, t["tinta2"], 500, "middle", halo))
    return svg(840, 200, "Ciclo do chefe: ficha, quebrar, brief, despachar, conferir (se não passou, corrigir em até 3 rodadas) "
               "e registrar; o registro volta para a ficha, que aprende", c)


def modo_god(t):
    fio = 'stroke="%s" stroke-width="1.5" fill="none"' % t["tinta3"]
    c = []
    c.append('<path d="M420 70V92M210 92H630M210 92V112M630 92V112" %s stroke-dasharray="4 4"/>' % fio)
    for cm in (210, 630):
        c.append('<path d="M%d 174V196M%d 196H%dM%d 196V214M%d 196V214M%d 196V214" %s/>'
                 % (cm, cm - 138, cm + 138, cm - 138, cm, cm + 138, fio))
    c += caixa(420, 8, 300, 62, "engenheiro · Fable", "3 visitas: planta, consulta, vistoria", t, destaque=True)
    for cm, frente in ((210, "frente A"), (630, "frente B")):
        c += caixa(cm, 112, 230, 62, "mestre de obras · Opus", frente + ": quebra, despacha, confere", t)
        for dx, nome, modelo in ((-138, "leitor", "Haiku"), (0, "executor", "Sonnet"), (138, "revisor", "Sonnet")):
            c += caixa(cm + dx, 214, 124, 56, nome, modelo, t)
    return svg(840, 278, "Modo god: um engenheiro em Fable faz 3 visitas; 2 mestres de obras em Opus tocam uma frente cada, "
               "cada um com leitor Haiku, executor Sonnet e revisor Sonnet", c)


def desenhar(d):
    if not os.path.isdir(IMG):
        os.makedirs(IMG)
    for nome_tema, t in TEMAS.items():
        for nome, conteudo in (("banner", banner(t)), ("numeros", blocos(t, d)),
                               ("tipos", grafico_tipos(t, d)), ("custo", grafico_custo(t, d)),
                               ("ciclo", ciclo(t)), ("modo-god", modo_god(t))):
            caminho = os.path.join(IMG, "%s-%s.svg" % (nome, nome_tema))
            with io.open(caminho, "w", encoding="utf-8", newline="\n") as f:
                f.write(conteudo)
            print("gravado:", caminho)


def main():
    ap = argparse.ArgumentParser(description="Graficos do README a partir do uso real")
    ap.add_argument("--coletar", action="store_true", help="relê o registro e os transcripts antes de desenhar")
    args = ap.parse_args()
    if args.coletar:
        dados = coletar()
    else:
        with io.open(DADOS, encoding="utf-8") as f:
            dados = json.load(f)
    desenhar(dados)


if __name__ == "__main__":
    main()
