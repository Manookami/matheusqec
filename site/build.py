"""Gera o site estático (vitrine de produtos) em site/dist a partir de dados/produtos.json e dados/precos.json.

Uso: python site/build.py
"""
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "robo"))
from comum import ARQ_PRECOS, ARQ_PRODUTOS, atalho, ler_json, link_produto, quedas, reais, resumo_preco  # noqa: E402

AQUI = Path(__file__).resolve().parent
DIST = Path(os.environ.get("QEC_DIST") or AQUI / "dist")
MESES = "jan fev mar abr mai jun jul ago set out nov dez".split()
POR_SECAO = 12  # cartões por categoria na página inicial
FITA_MINIMA = 5  # % de queda REAL (pelo histórico) a partir do qual aparece a fitinha

_SVG = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
ICONE_SOL = _SVG + '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
ICONE_TELA = _SVG + '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>'
ICONE_LUA = _SVG + '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
ICONE_BUSCA = _SVG + '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>'
ICONE_PLAY = _SVG + '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3z" fill="currentColor"/></svg>'


def versao(arquivo):
    """Código curto do conteúdo do arquivo: muda o endereço quando o arquivo muda (o navegador não usa cache velho)."""
    return hashlib.md5((AQUI / "static" / arquivo).read_bytes()).hexdigest()[:8]


def e(txt):
    return escape(str(txt or ""), quote=True)


def data_br(iso, ano=False):
    d = date.fromisoformat(iso)
    return f"{d.day:02d}/{d.month:02d}" + (f"/{d.year}" if ano else "")


def preco_html(valor):
    """R$ 1.899<sup>90</sup> como no ML."""
    inteiro = f"{int(valor):,}".replace(",", ".")
    cent = round((valor - int(valor)) * 100)
    return f'<span class="moeda">R$</span>{inteiro}' + (f"<sup>{cent:02d}</sup>" if cent else "")


def imagem(pid, dados, precos):
    return dados["produtos"][pid].get("imagem") or precos.get(pid, {}).get("imagem") or "/static/avatar.webp"


# ---------- cartão de produto ----------

def cartao(pid, dados, precos):
    prod = dados["produtos"][pid]
    r = resumo_preco(pid, dados, precos)
    p = precos.get(pid, {})
    esgotado = p.get("disponivel") is False
    url = link_produto(pid, dados, precos)
    fita = (f'<span class="fita">{r["desconto"]}% OFF</span>'
            if r and r["desconto"] >= FITA_MINIMA and not esgotado else "")
    selo = '<span class="selo">⭐ Recomendação do canal</span>' if prod.get("videos") else ""
    if r and not esgotado:
        antes = f'<s class="antes">{reais(r["original"])}</s>' if r["original"] else ""
        off = f'<span class="off">{r["desconto"]}% OFF</span>' if r["desconto"] else ""
        valor = f'{antes}<div class="preco">{preco_html(r["atual"])}{off}</div>'
        if r["atual"] <= r["minimo"] and len(r["pontos"]) > 3:
            valor += '<span class="minimo">Menor preço que já vi</span>'
    elif esgotado:
        valor = '<div class="esgotado">Esgotou no anúncio indicado: veja outras ofertas</div>'
    else:
        valor = '<div class="esgotado">Ver preço no Mercado Livre</div>'
    busca = f"{prod['nome']} {prod.get('busca', '')}".lower()
    atributos = (f'data-busca="{e(busca)}" data-cat="{e(prod.get("categoria"))}" '
                 f'data-preco="{r["atual"] if r and not esgotado else ""}" data-desc="{r["desconto"] if r and not esgotado else 0}"')
    return f"""<a class="card" href="{e(url)}" target="_blank" rel="sponsored nofollow noopener" {atributos}>
  {fita}<div class="card-foto"><img src="{e(imagem(pid, dados, precos))}" alt="{e(prod['nome'])}" loading="lazy" width="300" height="300"></div>
  <div class="card-info">{selo}<h3>{e(prod['nome'])}</h3>{valor}
  <span class="comprar">{'Ver ofertas' if esgotado else 'Comprar'}</span></div>
</a>"""


def grade(pids, dados, precos):
    return f'<div class="grade">{"".join(cartao(p, dados, precos) for p in pids)}</div>'


# ---------- moldura da página ----------

def pagina(titulo, corpo, dados, descricao="", caminho="/", ativo=""):
    site = dados["site"]
    url = site["url"].rstrip("/") + caminho
    cats = "".join(
        f'<a href="/{c["id"]}/" class="{"ativo" if c["id"] == ativo else ""}">{c["icone"]} {e(c["nome"])}</a>'
        for c in dados["categorias"])
    precos = ler_json(ARQ_PRECOS)
    datas = sorted(p.get("atualizado", "") for p in precos.values() if p.get("atualizado"))
    conferido = ""
    if datas:
        d = datetime.fromisoformat(datas[-1])
        conferido = f"Preços conferidos em {d:%d/%m/%Y} às {d:%H:%M}."
    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titulo)}</title>
<meta name="description" content="{e(descricao)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:title" content="{e(titulo)}"><meta property="og:description" content="{e(descricao)}">
<meta property="og:image" content="{e(site['url'].rstrip('/'))}/static/og.jpg"><meta property="og:url" content="{e(url)}">
<meta name="theme-color" content="#071026">
<link rel="icon" href="/static/favicon.png">
<link rel="preload" href="/static/Poppins-Bold.ttf" as="font" type="font/ttf" crossorigin>
<script>
// tema escolhido (claro/escuro) aplicado antes de desenhar a página; "sistema" segue o aparelho
try {{ var t = localStorage.getItem('tema'); if (t === 'claro' || t === 'escuro')
  document.documentElement.dataset.theme = t === 'claro' ? 'light' : 'dark'; }} catch (e) {{}}
</script>
<link rel="stylesheet" href="/static/estilo.css?v={versao('estilo.css')}">
</head><body>
<header class="topo">
  <div class="envolve topo-linha">
    <a class="marca" href="/"><img src="/static/avatar.webp" alt="" width="44" height="44"><b>Qual Eu <span>Compro?</span></b></a>
    <form class="busca" action="/busca/" role="search"><input name="q" type="search" placeholder="Buscar celular, TV, notebook…" aria-label="Buscar">
    <button aria-label="Buscar">{ICONE_BUSCA}</button></form>
    <div class="temas" role="group" aria-label="Tema">
      <button data-tema="claro" title="Modo claro" aria-label="Modo claro">{ICONE_SOL}</button>
      <button data-tema="sistema" title="Seguir o sistema" aria-label="Seguir o sistema">{ICONE_TELA}</button>
      <button data-tema="escuro" title="Modo escuro" aria-label="Modo escuro">{ICONE_LUA}</button>
    </div>
    <a class="yt" href="{e(site['youtube'])}" target="_blank" rel="noopener">{ICONE_PLAY}<span>Ver o canal</span></a>
  </div>
  <div class="envolve cats-caixa"><button class="cats-seta esq" type="button" aria-label="Ver abas anteriores" hidden>‹</button>
  <nav class="cats"><a href="/" class="{'ativo' if ativo == 'inicio' else ''}">🏠 Início</a><a href="/ofertas/" class="{'ativo' if ativo == 'ofertas' else ''}">🔥 Ofertas</a>{cats}</nav>
  <button class="cats-seta dir" type="button" aria-label="Ver mais abas" hidden>›</button></div>
</header>
<main class="envolve">{corpo}</main>
<footer class="rodape"><div class="envolve">
  <p><b>Qual Eu Compro?</b> · {e(site.get('descricao'))}
  <a href="{e(site['youtube'])}" target="_blank" rel="noopener">Ver o canal no YouTube →</a></p>
  <p class="miudo">Os botões levam ao Mercado Livre pelo link de afiliado do Matheus: se você comprar, ele ganha uma
  comissão e você não paga nada a mais. {conferido} O preço final é sempre o que aparece no Mercado Livre.</p>
</div></footer>
<script src="/static/loja.js?v={versao('loja.js')}" defer></script>
</body></html>"""


def preco_hoje(pid, dados, precos):
    r = resumo_preco(pid, dados, precos)
    return r["atual"] if r and precos.get(pid, {}).get("disponivel") is not False else None


def escolhidos(pids, dados, precos, n):
    """Ordem dos destaques: queda de preço real primeiro, depois recomendados no canal, depois o resto."""
    def chave(pid):
        r = resumo_preco(pid, dados, precos) or {}
        return (-r.get("desconto", 0), not dados["produtos"][pid].get("videos"))
    return sorted(pids, key=chave)[:n]


def slide_marca(dados):
    site = dados["site"]
    return f"""<div class="slide slide-marca">
  <div class="marca-texto"><span class="tarja">Matheus · Qual Eu Compro?</span>
  <h1>Eu pesquiso.<br><span>Você compra certo.</span></h1></div>
  <p class="descricao">{e(site.get('descricao'))}</p>
  <img class="avatar" src="/static/avatar.webp" alt="Avatar do Matheus" width="150" height="150">
</div>"""


def slide_categoria(c, dados, precos):
    pids = [p for p in dados["produtos"] if dados["produtos"][p].get("categoria") == c["id"] and preco_hoje(p, dados, precos)]
    if not pids:
        return ""
    top = escolhidos(pids, dados, precos, 3)
    valores = sorted(preco_hoje(p, dados, precos) for p in pids)
    mediana = valores[len(valores) // 2]
    # "a partir de": o mais barato que ainda faz sentido na categoria (acessório perdido não conta)
    menor = min(v for v in valores if v >= mediana * 0.15)
    fotos = "".join(f'<span class="mini"><img src="{e(imagem(p, dados, precos))}" alt="" loading="lazy"></span>' for p in top)
    return f"""<a class="slide slide-cat" href="/{c['id']}/">
  <div class="slide-texto"><span class="tarja">{c['icone']} {e(c['nome'])}</span>
  <h2>{e(c.get('banner') or c['nome'])}</h2><p>{e(c.get('banner_sub'))}</p>
  <span class="slide-cta">A partir de <b>{reais(menor)}</b> · Ver todos →</span></div>
  <div class="minis">{fotos}</div>
</a>"""


def carrossel(dados, precos):
    slides = [slide_marca(dados)] + [s for c in dados["categorias"] if (s := slide_categoria(c, dados, precos))]
    pontos = "".join(f'<button aria-label="Banner {i + 1}"></button>' for i in range(len(slides)))
    return f"""<section class="carrossel" aria-roledescription="carrossel">
  <div class="trilho">{''.join(slides)}</div>
  <div class="pontos">{pontos}</div>
</section>"""


def secao(titulo, pids, dados, precos, link=None, sid="", extra=""):
    if not pids:
        return ""
    ver = f'<a class="ver-todos" href="{link}">Ver todos ›</a>' if link else ""
    return (f'<section class="secao" data-secao="{e(sid)}"><div class="secao-topo"><h2>{titulo}</h2>{ver}{extra}</div>'
            f'{grade(pids, dados, precos)}</section>')


def gerar_home(dados, precos):
    todos = list(dados["produtos"])
    destaques = escolhidos([p for p in todos if preco_hoje(p, dados, precos)], dados, precos, 10)
    abas = ('<div class="abas" data-abas="destaques"><button class="ativo" data-cat="">Todos</button>'
            + "".join(f'<button data-cat="{c["id"]}">{e(c["nome"])}</button>' for c in dados["categorias"]
                      if any(dados["produtos"][p]["categoria"] == c["id"] for p in destaques))
            + "</div>")
    canal = [p for p in escolhidos(todos, dados, precos, len(todos)) if dados["produtos"][p].get("videos")]
    corpo = carrossel(dados, precos) + secao("🔥 Destaques", destaques, dados, precos, sid="destaques", extra=abas)
    corpo += secao("⭐ Recomendados no canal", canal, dados, precos, sid="canal")
    for c in dados["categorias"]:
        pids = [p for p in todos if dados["produtos"][p].get("categoria") == c["id"]]
        # na página inicial só uma vitrine de cada categoria; o resto fica na página dela
        corpo += secao(f'{c["icone"]} {e(c["nome"])} <small>{len(pids)} produtos</small>', pids[:POR_SECAO],
                       dados, precos, f'/{c["id"]}/', c["id"])
    return pagina("Qual Eu Compro? · as indicações do Matheus com o menor preço", corpo, dados,
                  "Celulares, TVs, notebooks, tablets, videogames e smartwatches indicados no canal Qual Eu Compro, com o preço de hoje no Mercado Livre.",
                  ativo="inicio")


def gerar_busca(dados, precos):
    """Todos os produtos numa página só; o loja.js mostra apenas os que batem com ?q=."""
    pids = list(dados["produtos"])
    corpo = f"""<p class="trilha"><a href="/">Início</a> › Busca</p>
<div class="cat-topo"><h1>🔍 <span data-termo>Buscar</span> <small><span data-contagem>0</span> produtos</small></h1>{ORDENS}</div>
<div class="cat-corpo">{filtros(pids, dados, precos)}
<div data-busca-pagina>{grade(pids, dados, precos)}<p id="vazio" class="vazio" hidden>Nenhum produto encontrado. Tente outra palavra.</p></div></div>"""
    return pagina("Buscar · Qual Eu Compro?", corpo, dados, "Busque entre todos os produtos do Qual Eu Compro?", "/busca/")


def faixas_preco(valores):
    """Três faixas de preço "redondas" a partir dos preços da categoria (terços)."""
    v = sorted(valores)
    if len(v) < 3:
        return []
    passo = 500 if v[-1] > 3000 else 100
    t1 = max(passo, round(v[len(v) // 3] / passo) * passo)
    t2 = max(t1 + passo, round(v[2 * len(v) // 3] / passo) * passo)
    return [(0, t1, f"Até {reais(t1)}"), (t1, t2, f"{reais(t1)} a {reais(t2)}"), (t2, 10 ** 9, f"Acima de {reais(t2)}")]


def filtros(pids, dados, precos):
    valores = [x for p in pids if (x := preco_hoje(p, dados, precos))]
    com_desc = sum(1 for p in pids if (resumo_preco(p, dados, precos) or {}).get("desconto", 0) >= FITA_MINIMA)
    opcoes = [f'<label><input type="radio" name="faixa" value="" checked><span>Qualquer preço</span><i>{len(pids)}</i></label>']
    for a, b, rotulo in faixas_preco(valores):
        n = sum(1 for x in valores if a < x <= b)
        opcoes.append(f'<label><input type="radio" name="faixa" value="{a}-{b}"><span>{rotulo}</span><i>{n}</i></label>')
    # <details>: aberto no computador, recolhido no celular (o loja.js fecha em tela pequena)
    return f"""<details class="filtros" open>
  <summary class="filtros-topo"><b>Filtros</b><span class="filtros-seta" aria-hidden="true">▾</span></summary>
  <fieldset><legend>Preço</legend>{''.join(opcoes)}</fieldset>
  <label class="chave"><span><b>Só com desconto real</b><small>{com_desc} produto{'s' if com_desc != 1 else ''} com preço em queda</small></span>
  <input type="checkbox" data-so-desconto><i></i></label>
  <button type="button" class="limpar" data-limpar>Limpar filtros</button>
</details>"""


ORDENS = '''<div class="ordem" role="group" aria-label="Ordenar por"><span>Ordenar por</span>
<button class="ativo" data-ordem="relevancia">Relevância</button><button data-ordem="menor">Menor preço</button>
<button data-ordem="maior">Maior preço</button><button data-ordem="desconto">Maior desconto</button></div>'''


def gerar_categoria(c, dados, precos):
    pids = escolhidos([p for p in dados["produtos"] if dados["produtos"][p].get("categoria") == c["id"]], dados, precos, 999)
    corpo = f"""<p class="trilha"><a href="/">Início</a> › {e(c["nome"])}</p>
<div class="cat-topo"><h1>{c["icone"]} {e(c["nome"])} <small><span data-contagem>{len(pids)}</span> de {len(pids)} produtos</small></h1>{ORDENS}</div>
<div class="cat-corpo">{filtros(pids, dados, precos)}
<div>{grade(pids, dados, precos)}<p id="vazio" class="vazio" hidden>Nenhum produto com esses filtros.</p></div></div>"""
    return pagina(f'{c["nome"]} · Qual Eu Compro?', corpo, dados,
                  f'{c["nome"]} indicados no canal Qual Eu Compro com o preço de hoje.', f'/{c["id"]}/', c["id"])


def gerar_ofertas(dados, precos):
    pids = [p for p in escolhidos(list(dados["produtos"]), dados, precos, 999)
            if (resumo_preco(p, dados, precos) or {}).get("desconto", 0) >= FITA_MINIMA]
    caiu = [q["produto"] for q in quedas(dados, precos) if q["produto"] not in pids]
    corpo = '<p class="trilha"><a href="/">Início</a> › Ofertas</p>'
    corpo += secao(f"🔥 Preço caiu de verdade <small>{len(pids)} produtos</small>", pids, dados, precos, sid="ofertas")
    corpo += secao("📉 Caiu nos últimos dias", caiu, dados, precos, sid="caiu")
    if not pids and not caiu:
        corpo += ('<div class="painel vazio-ofertas"><h3>Nenhuma queda de preço de verdade agora</h3>'
                  '<p>Aqui só entra produto cujo preço caiu em relação ao que ele custou nos últimos 30 dias. '
                  'O "de R$ X por R$ Y" dos anúncios não conta.</p></div>')
    return pagina("Ofertas · Qual Eu Compro?", corpo, dados,
                  "Os produtos indicados no canal Qual Eu Compro que baixaram de preço de verdade.", "/ofertas/", "ofertas")

# ---------- página de análise (vídeo) ----------

def grafico(pontos):
    """Histórico de preço em SVG puro (eixo x proporcional ao tempo)."""
    if len(pontos) < 2:
        return ""
    W, H, ml, mr, mt, mb = 640, 220, 8, 8, 28, 30
    dias = [date.fromisoformat(p["data"]).toordinal() for p in pontos]
    vals = [p["preco"] for p in pontos]
    d0, d1 = min(dias), max(dias)
    v0, v1 = min(vals) * 0.8, max(vals) * 1.05
    x = lambda d: ml + (d - d0) / max(1, d1 - d0) * (W - ml - mr)
    y = lambda v: mt + (v1 - v) / (v1 - v0) * (H - mt - mb)
    xy = [(x(d), y(v)) for d, v in zip(dias, vals)]
    linha = " ".join(f"{a:.1f},{b:.1f}" for a, b in xy)
    area = f"{xy[0][0]:.1f},{H - mb} " + linha + f" {xy[-1][0]:.1f},{H - mb}"
    imin = vals.index(min(vals))
    pts = "".join(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="{5 if i in (imin, len(xy) - 1) else 3.5}" '
                  f'fill="{"#4ade80" if i == imin else "#FFF300"}"><title>{data_br(p["data"])}: {reais(p["preco"])}</title></circle>'
                  for i, ((a, b), p) in enumerate(zip(xy, pontos)))
    rotulos = ""
    for i, cor, pref in ((imin, "#4ade80", "menor "), (len(xy) - 1, "#FFF300", "hoje ")):
        if pref == "hoje " and imin == len(xy) - 1:
            continue
        a, b = xy[i]
        b = b + 36 if pref == "menor " else b
        anc = "end" if a > W * .75 else ("start" if a < W * .25 else "middle")
        rotulos += (f'<text x="{a:.1f}" y="{b - 12:.1f}" fill="{cor}" font-size="18" font-weight="700" '
                    f'text-anchor="{anc}">{pref}{reais(vals[i])}</text>')
    eixo = "".join(
        f'<text x="{x(d):.1f}" y="{H - 8}" fill="#a3a3a3" font-size="14" text-anchor="{"start" if d == d0 else "end"}">'
        f'{MESES[date.fromisoformat(p["data"]).month - 1]} {date.fromisoformat(p["data"]).year}</text>'
        for d, p in ((dias[0], pontos[0]), (dias[-1], pontos[-1])))
    return (f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Histórico de preço">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF300" stop-opacity=".25"/>'
            f'<stop offset="1" stop-color="#FFF300" stop-opacity="0"/></linearGradient></defs>'
            f'<line x1="{ml}" x2="{W - mr}" y1="{H - mb}" y2="{H - mb}" stroke="#2a2a2a"/>'
            f'<polygon points="{area}" fill="url(#g)"/>'
            f'<polyline points="{linha}" fill="none" stroke="#FFF300" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>'
            + pts + rotulos + eixo + "</svg>")


def gerar_analise(pg, dados, precos):
    esc = pg["escolha"]
    pid = esc["produto"]
    r = resumo_preco(pid, dados, precos)
    datas = "".join(
        f'<div class="data"><b>{(date.fromisoformat(d["data"]) - date.today()).days} dias</b>{e(d["nome"])} · {data_br(d["data"])}</div>'
        for d in pg.get("datas", []) if date.fromisoformat(d["data"]) >= date.today())
    alts = [a["produto"] for a in pg.get("alternativas", []) if a["produto"] in dados["produtos"]]
    para = "".join(f'<li><b>{e(dados["produtos"][a["produto"]]["nome"])}</b>: {e(a["para"])}</li>'
                   for a in pg.get("alternativas", []) if a["produto"] in dados["produtos"])
    corpo = f"""<p class="trilha"><a href="/">Início</a> › Análise</p>
<section class="analise">
  <div class="analise-card">{cartao(pid, dados, precos)}</div>
  <div class="painel"><span class="selo">⭐ {e(esc.get('selo', 'Minha escolha'))}</span>
  <h1>{e(pg['titulo'])}</h1><p>{e(pg.get('resumo'))}</p>
  {f'<div class="grafico"><h3>Histórico de preço</h3>{grafico(r["pontos"])}</div>' if r and len(r["pontos"]) > 1 else ''}
  </div>
</section>
<section class="duas">
  <div class="painel"><h3>Por que eu escolhi</h3><ul class="lista pros">{''.join(f'<li>{e(x)}</li>' for x in esc.get('pros', []))}</ul></div>
  <div class="painel"><h3>Pontos fracos</h3><ul class="lista contras">{''.join(f'<li>{e(x)}</li>' for x in esc.get('contras', []))}</ul></div>
</section>
{f'<section class="painel"><h3>Quando comprar</h3><p>{e(pg["quando_comprar"])}</p><div class="datas">{datas}</div></section>' if pg.get('quando_comprar') else ''}
{f'<section class="painel"><h3>Pra quem ele não é</h3><ul class="lista">{para}</ul></section>' if para else ''}
{secao('Alternativas', alts, dados, precos, sid='alternativas')}"""
    return pagina(f"{pg['titulo']} · Qual Eu Compro?", corpo, dados, pg.get("resumo", ""), f"/{pg['slug']}/")


# ---------- link curto (descrição do vídeo) ----------

def gerar_redirecionamento(pid, dados, precos):
    """Página do link curto: manda direto pro link de afiliado (meta refresh + JS, com botão de reserva)."""
    destino = link_produto(pid, dados, precos)
    nome = dados["produtos"][pid]["nome"]
    js = json.dumps(destino).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer-when-downgrade">
<title>{e(nome)} · Mercado Livre</title>
<meta property="og:title" content="{e(nome)} · Qual Eu Compro?"><meta property="og:image" content="{e(imagem(pid, dados, precos))}">
<meta http-equiv="refresh" content="0;url={e(destino)}">
<script>location.replace({js});</script>
<link rel="icon" href="/static/favicon.png">
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#071026;color:#f2f2f2;
font:16px system-ui,sans-serif;text-align:center;padding:16px}}img{{width:96px;height:96px;border-radius:18px}}
a{{display:inline-block;margin-top:16px;background:#FFF300;color:#000;font-weight:700;padding:14px 22px;
border-radius:8px;text-decoration:none}}</style>
</head><body><div><img src="/static/avatar.webp" alt=""><p>Te levando pro <b>{e(nome)}</b> no Mercado Livre…</p>
<a href="{e(destino)}" rel="sponsored nofollow">Abrir no Mercado Livre</a></div></body></html>"""


def main():
    dados = ler_json(ARQ_PRODUTOS)
    precos = ler_json(ARQ_PRECOS)
    reservados = ({"static", "ofertas", "busca", "ir", "index.html", "404.html"} | {pg["slug"] for pg in dados["paginas"]}
                  | {c["id"] for c in dados["categorias"]})
    atalhos = {}
    for pid in dados["produtos"]:
        a = atalho(pid, dados)
        if not re.fullmatch(r"[a-z0-9-]+(/[a-z0-9-]+)?", a) or a in reservados or a in atalhos:
            raise SystemExit(f"ERRO: atalho inválido ou repetido para {pid}: {a!r}")
        atalhos[a] = pid
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "static").mkdir(parents=True)
    for f in (AQUI / "static").iterdir():
        shutil.copy(f, DIST / "static" / f.name)

    arquivos = {"index.html": gerar_home(dados, precos), "ofertas/index.html": gerar_ofertas(dados, precos),
                "busca/index.html": gerar_busca(dados, precos)}
    for c in dados["categorias"]:
        arquivos[f"{c['id']}/index.html"] = gerar_categoria(c, dados, precos)
    for pg in dados["paginas"]:
        arquivos[f"{pg['slug']}/index.html"] = gerar_analise(pg, dados, precos)
    for pid in dados["produtos"]:
        arquivos[f"ir/{pid}/index.html"] = arquivos[f"{atalho(pid, dados)}/index.html"] = gerar_redirecionamento(pid, dados, precos)
    arquivos["404.html"] = pagina("Página não encontrada", '<section class="secao"><h2>Ops, essa página não existe.</h2>'
                                  '<p><a href="/">Voltar para a loja</a></p></section>', dados)
    for nome, html in arquivos.items():
        (DIST / nome).parent.mkdir(parents=True, exist_ok=True)
        (DIST / nome).write_text(html, encoding="utf-8")

    base = dados["site"]["url"].rstrip("/")
    urls = ([base + "/", base + "/ofertas/"] + [f"{base}/{c['id']}/" for c in dados["categorias"]]
            + [f"{base}/{pg['slug']}/" for pg in dados["paginas"]])
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                                      + "".join(f"<url><loc>{u}</loc><lastmod>{date.today()}</lastmod></url>" for u in urls)
                                      + "</urlset>\n", encoding="utf-8")
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")
    if dados["site"].get("dominio"):
        (DIST / "CNAME").write_text(dados["site"]["dominio"] + "\n", encoding="utf-8")
    linhas = [f"{base}/{a}  ->  {dados['produtos'][pid]['nome']}"
              + ("" if dados["produtos"][pid].get("afiliado") else "   (SEM link de afiliado: vai pra busca)")
              for a, pid in atalhos.items()]
    (DIST / "links.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"site gerado em {DIST} ({len(arquivos)} páginas)\nLinks curtos para a descrição:\n  " + "\n  ".join(linhas))


if __name__ == "__main__":
    main()
