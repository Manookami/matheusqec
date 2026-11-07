"""Robô de preços: consulta no Mercado Livre o preço e o estoque de cada produto do catálogo.

Roda sozinho no GitHub Actions (ver .github/workflows/diario.yml). Precisa de um app de desenvolvedor do ML:
  ML_CLIENT_ID, ML_CLIENT_SECRET, ML_REFRESH_TOKEN  (variáveis de ambiente / secrets)
O refresh token do ML só pode ser usado uma vez: o novo é gravado em ML_NOVO_REFRESH_ARQ para o workflow
salvar de volta no secret. Sem credenciais, o robô avisa e sai sem erro (o site continua com o último preço).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from comum import ARQ_PRECOS, ARQ_PRODUTOS, agora_iso, gravar_json, hoje, id_ml, ler_json

API = "https://api.mercadolibre.com"


def pedir(caminho, token=None, dados=None):
    req = urllib.request.Request(API + caminho, data=dados, headers={"Accept": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if dados:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    for tentativa in range(4):  # conexão derrubada / lentidão: espera e tenta de novo
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or tentativa == 3:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            if tentativa == 3:
                raise
        time.sleep(2 * (tentativa + 1))


def token_ml():
    cid, segredo, refresh = (os.environ.get(k) for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "ML_REFRESH_TOKEN"))
    if not (cid and segredo and refresh):
        return None
    corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": cid,
                                    "client_secret": segredo, "refresh_token": refresh}).encode()
    resp = pedir("/oauth/token", dados=corpo)
    novo = resp.get("refresh_token")
    destino = os.environ.get("ML_NOVO_REFRESH_ARQ")
    if novo and destino:
        with open(destino, "w") as f:
            f.write(novo)
    return resp["access_token"]


def resolver(url):
    """Segue o link curto de afiliado (meli.la) até o endereço do produto, para achar o código MLB."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            final = r.geturl()
    except urllib.error.HTTPError as e:  # página de verificação do ML ainda traz o destino no endereço
        final = e.geturl() or url
    except Exception:
        return None
    return urllib.parse.unquote(final)


def foto(pics):
    for p in pics or []:
        url = p.get("secure_url") or p.get("url")
        if url:
            return url.replace("http://", "https://")
    return None


REPUTACAO_BOA = ("4_light_green", "5_green")
_vendedores = {}  # reputação já consultada nesta rodada


def vendedor_confiavel(oferta, token):
    """Loja oficial ou vendedor com reputação verde. Conta nova sem reputação costuma ter o preço
    "bom demais" (ex.: DualSense Edge a R$ 607 quando custa R$ 1.300) e não entra no site."""
    if oferta.get("official_store_id"):
        return True
    vid = oferta.get("seller_id")
    if vid not in _vendedores:
        try:
            rep = pedir(f"/users/{vid}", token).get("seller_reputation") or {}
            _vendedores[vid] = rep.get("level_id") in REPUTACAO_BOA
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            return False  # não deu para conferir: não arrisca
    return _vendedores[vid]


def consulta_produto(mlb, token):
    """Produto de catálogo (/p/MLB...): o preço que a pessoa vê ao abrir a página é o do vendedor em
    destaque (buy box, escolhido pelo próprio ML); sem ele, a oferta mais barata de vendedor confiável."""
    cat = pedir(f"/products/{mlb}", token)
    imagem = foto(cat.get("pictures"))
    melhor = cat.get("buy_box_winner")
    if not (melhor and melhor.get("price")):
        try:
            ofertas = pedir(f"/products/{mlb}/items?limit=50", token).get("results", [])
        except urllib.error.HTTPError:
            ofertas = []
        ofertas = sorted((o for o in ofertas if o.get("price") and o.get("condition", "new") == "new"),
                         key=lambda o: o["price"])
        if not ofertas:
            return {"disponivel": False, "imagem": imagem}
        melhor = next((o for o in ofertas[:12] if vendedor_confiavel(o, token)), None)
        if not melhor:  # só tem vendedor sem reputação: não mostra preço (o site cai em "Ver preço")
            return {"disponivel": True, "preco": None, "imagem": imagem}
    return {
        "disponivel": True,
        "preco": melhor["price"],
        "preco_original": melhor.get("original_price"),
        "frete_gratis": bool((melhor.get("shipping") or {}).get("free_shipping")),
        "imagem": imagem,
    }


def consulta_item(mlb, token):
    it = pedir(f"/items/{mlb}", token)
    ativo = it.get("status") == "active" and (it.get("available_quantity") or 0) > 0
    return {
        "disponivel": ativo,
        "preco": it.get("price") if ativo else None,
        "preco_original": it.get("original_price") if ativo else None,
        "frete_gratis": bool((it.get("shipping") or {}).get("free_shipping")),
        "imagem": foto(it.get("pictures")) or it.get("secure_thumbnail"),
    }


def main():
    produtos = ler_json(ARQ_PRODUTOS)
    precos = ler_json(ARQ_PRECOS)
    try:
        token = token_ml()
    except urllib.error.HTTPError as e:
        print(f"ERRO: o Mercado Livre recusou o token ({e.code}). Refaça a autorização (LEIA-ME).", file=sys.stderr)
        return 1
    if not token:
        print("Sem credenciais do Mercado Livre: preços não atualizados (o site usa os últimos).")
        return 0

    lidos = 0
    for pid, cat in produtos["produtos"].items():
        ref = (("item", cat["item"]) if cat.get("item") else None) or id_ml(cat.get("ml")) \
            or id_ml(precos.get(pid, {}).get("ml_resolvido"))
        if not ref and cat.get("afiliado"):
            destino = resolver(cat["afiliado"])
            ref = id_ml(destino)
            if ref:
                precos.setdefault(pid, {"historico": []})["ml_resolvido"] = destino
        if not ref:
            print(f"- {pid}: sem link do ML ainda, pulando")
            continue
        time.sleep(0.25)  # sem pressa: o ML derruba conexões quando as consultas vêm coladas
        try:
            info = (consulta_produto if ref[0] == "produto" else consulta_item)(ref[1], token)
        except urllib.error.HTTPError as e:
            print(f"- {pid}: erro {e.code} no ML, mantendo o último preço")
            continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            print(f"- {pid}: falha de conexão ({e}), mantendo o último preço")
            continue
        lidos += 1
        if lidos % 50 == 0:  # salva o progresso de tempos em tempos
            gravar_json(ARQ_PRECOS, precos)
        reg = precos.setdefault(pid, {"historico": []})
        reg.update({k: v for k, v in info.items() if k != "preco" and v is not None})
        reg["disponivel"] = info["disponivel"]
        reg["preco_original"] = info.get("preco_original")  # sem promoção hoje -> some a fitinha
        reg.pop("fonte", None)
        reg["atualizado"] = agora_iso()
        if info.get("preco"):
            # um ponto por dia: a leitura mais recente substitui a anterior do mesmo dia
            h = [x for x in reg["historico"] if x["data"] != hoje()]
            reg["historico"] = h + [{"data": hoje(), "preco": info["preco"]}]
        print(f"- {pid}: {'R$ %.2f' % info['preco'] if info.get('preco') else 'indisponível'}")

    gravar_json(ARQ_PRECOS, precos)
    print(f"\n{lidos} de {len(produtos['produtos'])} produtos consultados com sucesso.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
