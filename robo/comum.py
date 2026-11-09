"""Funções compartilhadas pelo robô de preços, pelo site e pelo bot do WhatsApp."""
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse, quote

RAIZ = Path(__file__).resolve().parent.parent
DADOS = Path(os.environ.get("QEC_DADOS") or RAIZ / "dados")  # QEC_DADOS: pasta alternativa (testes)
ARQ_PRODUTOS = DADOS / "produtos.json"
ARQ_PRECOS = DADOS / "precos.json"


def ler_json(caminho, padrao=None):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {} if padrao is None else padrao


def gravar_json(caminho, dados):
    Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def hoje():
    return date.today().isoformat()


def reais(valor):
    """1749.9 -> 'R$ 1.749,90'; 1749 -> 'R$ 1.749'."""
    if valor is None:
        return ""
    inteiro = int(valor)
    centavos = round((valor - inteiro) * 100)
    txt = f"{inteiro:,}".replace(",", ".")
    return f"R$ {txt},{centavos:02d}" if centavos else f"R$ {txt}"


# ---------- Mercado Livre: ids e links ----------

def id_ml(url):
    """Devolve ('produto', 'MLB123') para links /p/, ('item', 'MLB123') para anúncios, ou None."""
    if not url:
        return None
    m = re.search(r"/p/(MLB\d+)", url)
    if m:
        return ("produto", m.group(1))
    if re.search(r"/up/MLBU\d+", url):
        return None  # página de "produto do usuário": o robô usa o campo `item` do catálogo
    m = re.search(r"(MLB)-?(\d{6,})", url)
    if m:
        return ("item", m.group(1) + m.group(2))
    return None


def link_afiliado(url, afiliado):
    """Coloca a identificação de afiliado (matt_word/matt_tool) no link do ML."""
    if not url:
        return url
    word, tool = (afiliado or {}).get("matt_word"), (afiliado or {}).get("matt_tool")
    if not word or "meli.la" in url:
        return url
    partes = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(partes.query) if k not in ("matt_word", "matt_tool")]
    qs += [("matt_word", word)] + ([("matt_tool", tool)] if tool else [])
    return urlunparse(partes._replace(query=urlencode(qs), fragment=""))


def link_busca(cat):
    return "https://lista.mercadolivre.com.br/" + quote(cat.get("busca") or cat["nome"]).replace("%20", "-")


def link_produto(pid, produtos, precos):
    """Para onde o clique vai:
    1. o link de afiliado que o Matheus gerou no painel do ML (enquanto o produto tem estoque);
    2. se esgotou ou ainda não tem link: a busca do produto no ML, com a tag de afiliado."""
    cat = produtos["produtos"][pid]
    disponivel = precos.get(pid, {}).get("disponivel", True)
    if cat.get("afiliado") and disponivel:
        return cat["afiliado"]
    return link_afiliado(link_busca(cat), produtos.get("afiliado"))


def atalho(pid, produtos):
    """Link curto do site que redireciona pro afiliado (vai na descrição do vídeo)."""
    return produtos["produtos"][pid].get("atalho") or f"ir/{pid}"


# ---------- histórico e quedas de preço ----------

def historico(pid, produtos, precos):
    """Histórico do robô somado ao histórico inicial (pesquisa do vídeo), um ponto por dia."""
    pontos = {h["data"]: h for h in produtos["produtos"][pid].get("historico_inicial", [])}
    for h in precos.get(pid, {}).get("historico", []):
        pontos[h["data"]] = h
    return [pontos[d] for d in sorted(pontos)]


DESCONTO_JANELA = 30      # dias usados para saber o preço "normal" do produto
DESCONTO_MIN_DIAS = 7     # histórico mínimo antes de afirmar que caiu
DESCONTO_MIN = 0.05       # queda mínima para valer como desconto
PRECO_VALIDO_DIAS = 3     # preço mais velho que isso vira "Ver preço no Mercado Livre"
DESCONTO_MAX = 0.60       # acima disso não é promoção: costuma ser golpe ou anúncio errado
DESCONTO_MIN_LEITURAS = 3 # leituras de preço necessárias (com o robô diário, isso sai em 3 dias)
DESCONTO_CONFIRMAR = 0.30 # queda desse tamanho ou maior precisa aparecer em 2 leituras seguidas


def desconto_real(h, hoje_iso=None):
    """Desconto de verdade, medido pelo NOSSO histórico (não pelo "de/por" que o anúncio mostra).

    Preço normal = mediana dos preços dos últimos 30 dias antes de hoje. Só vale se já existe pelo menos
    7 dias de histórico e o preço de hoje está 5% ou mais abaixo do normal. Preço parado há tempos com
    "de R$ X" inflado no anúncio não ganha fitinha; subir e baixar em seguida também não engana a mediana."""
    if len(h) < DESCONTO_MIN_LEITURAS:  # 2 leituras não provam nada (pode ser outro vendedor/cor)
        return None
    atual = h[-1]
    d_atual = date.fromisoformat(hoje_iso or atual["data"])
    if date.fromisoformat(h[0]["data"]) > d_atual - timedelta(days=DESCONTO_MIN_DIAS):
        return None
    inicio = (d_atual - timedelta(days=DESCONTO_JANELA)).isoformat()
    antes = sorted(x["preco"] for x in h[:-1] if x["data"] >= inicio)
    if not antes:  # sem leituras recentes: compara com a última leitura conhecida
        antes = [h[-2]["preco"]]
    meio = len(antes) // 2
    referencia = antes[meio] if len(antes) % 2 else (antes[meio - 1] + antes[meio]) / 2
    queda = 1 - atual["preco"] / referencia
    if queda < DESCONTO_MIN or queda > DESCONTO_MAX:  # queda absurda = anúncio suspeito ou erro, não promoção
        return None
    if queda >= DESCONTO_CONFIRMAR and h[-2]["preco"] > atual["preco"] * 1.05:
        return None  # queda grande que apareceu num dia só: espera a próxima leitura confirmar
    return {"referencia": referencia, "desconto": round(100 * queda)}


def resumo_preco(pid, produtos, precos):
    h = historico(pid, produtos, precos)
    if not h:
        return None
    atual = h[-1]
    minimo = min(h, key=lambda x: x["preco"])
    maximo = max(h, key=lambda x: x["preco"])
    recente = [x["preco"] for x in h if x["data"] >= (date.fromisoformat(atual["data"]) - timedelta(days=30)).isoformat()]
    real = desconto_real(h)
    return {
        "original": real["referencia"] if real else None,
        "desconto": real["desconto"] if real else 0,
        "preco_ml_antes": (precos.get(pid) or {}).get("preco_original"),  # "de/por" do ML: só informativo
        "atual": atual["preco"],
        "data": atual["data"],
        "minimo": minimo["preco"],
        "data_minimo": minimo["data"],
        "maximo": maximo["preco"],
        "media_30d": sum(recente) / len(recente),
        "pontos": h,
        "ao_vivo": pid in precos and bool(precos[pid].get("historico")),
        # preço confirmado há no máximo 3 dias; mais velho que isso o site não mostra (pode ter mudado)
        "recente": date.fromisoformat(atual["data"]) >= date.today() - timedelta(days=PRECO_VALIDO_DIAS),
    }


def limite_historia(iso):
    return (date.fromisoformat(iso) - timedelta(days=30)).isoformat()


MARCAS = ("samsung", "galaxy", "motorola", "moto ", "xiaomi", "redmi", "poco", "apple", "iphone", "ipad", "realme",
          "oppo", "honor", "infinix", "lg ", "tcl", "philco", "aoc", "philips", "lenovo", "ideapad", "acer", "asus",
          "dell", "positivo", "vaio", "hp ", "hisense", "roku", "multi", "britânia", "britania", "semp", "aiwa",
          "jbl", "sony", "playstation", "dualsense", "xbox", "microsoft", "nintendo", "switch", "gamesir", "flydigi",
          "8bitdo", "havit", "redragon", "hyperx", "logitech", "fortrek", "evolut", "qcy", "anker", "soundcore",
          "baseus", "ugreen", "amazfit", "haylou", "dapon", "kingston", "adata", "patriot", "tp-link", "mercusys",
          "intelbras", "huawei", "ubiquiti", "amazon", "echo", "alexa", "mondial", "electrolux", "oster", "midea",
          "elgin", "arno", "nescafé", "nespresso", "stanley", "termolar", "oral-b", "ventisol", "wap", "thunderx3",
          "akko", "monsgeek", "knup", "i2go", "plus do brasil", "r36s", "ipega", "qrd", "oneodio", "gta", "rog",
          "predator", "nitro", "tres", "3 corações", "pulse", "edifier", "kaidi")


def marca_conhecida(nome):
    n = " " + nome.lower() + " "
    return any(m in n for m in MARCAS)


def lista_videos(p):
    v = p.get("videos") or []
    return [v] if isinstance(v, str) else list(v)  # o hub às vezes grava um vídeo só como texto


def pesos_categoria(produtos):
    """Categoria que o canal mais cobre vem primeiro: conta em quantos vídeos cada categoria aparece.
    Achados gerais ficam sempre por último."""
    vids = {}
    for p in produtos["produtos"].values():
        for v in lista_videos(p):
            vids.setdefault(p["categoria"], set()).add(v)
    ordem = sorted((c["id"] for c in produtos["categorias"] if c["id"] != "gerais"), key=lambda c: -len(vids.get(c, ())))
    return {c: i for i, c in enumerate(ordem)} | {"gerais": 99}


def relevancia(pid, produtos, _cache={}):
    """Chave de ordem (menor = mais importante): 1º produtos dos vídeos do canal (mais vídeos, mais acima),
    depois categorias que o canal mais cobre, marca conhecida antes de genérico, achados gerais por último."""
    chave = id(produtos)
    if _cache.get("id") != chave:
        _cache.clear()
        _cache.update(id=chave, pesos=pesos_categoria(produtos))
    p = produtos["produtos"][pid]
    nv = len(lista_videos(p))
    if nv:
        return (0, -nv, 0)
    if p["categoria"] == "gerais":
        return (3, 0, 0)
    return (1 if marca_conhecida(p["nome"]) else 2, _cache["pesos"].get(p["categoria"], 50), 0)


def quedas(produtos, precos, queda_minima=0.05, dias=7):
    """Produtos cujo preço de hoje caiu em relação ao maior preço dos últimos `dias` dias."""
    achados = []
    for pid in produtos["produtos"]:
        r = resumo_preco(pid, produtos, precos)
        if not r or not r["ao_vivo"] or precos[pid].get("disponivel") is False:
            continue
        limite = (date.fromisoformat(r["data"]) - timedelta(days=dias)).isoformat()
        janela = [x["preco"] for x in r["pontos"] if limite <= x["data"] < r["data"]]
        if not janela:
            continue
        antes = max(janela)
        queda = 1 - r["atual"] / antes
        if queda >= queda_minima:
            achados.append({
                "produto": pid,
                "antes": antes,
                "agora": r["atual"],
                "queda": queda,
                # só afirma "menor da história" com pelo menos 30 dias de histórico
                "menor_da_historia": r["atual"] <= r["minimo"] and r["pontos"][0]["data"] <= limite_historia(r["data"]),
                "data": r["data"],
            })
    return sorted(achados, key=lambda q: -q["queda"])


def agora_iso():
    return datetime.now().isoformat(timespec="seconds")
