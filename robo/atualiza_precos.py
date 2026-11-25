"""Robô de preços: consulta no Mercado Livre o preço e o estoque de cada produto do catálogo.

Roda sozinho no GitHub Actions (ver .github/workflows/diario.yml). Precisa de um app de desenvolvedor do ML:
  ML_CLIENT_ID, ML_CLIENT_SECRET, ML_REFRESH_TOKEN  (variáveis de ambiente / secrets)
O refresh token do ML só pode ser usado uma vez: o novo é gravado em ML_NOVO_REFRESH_ARQ para o workflow
salvar de volta no secret. Sem credenciais, o robô avisa e sai sem erro (o site continua com o último preço).
"""
import json
import re
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
        except urllib.error.HTTPError as e:
            # 404 = o produto não tem nenhuma oferta (esgotado de verdade). Qualquer outro erro (ex.: 403
            # "PolicyAgent", que o ML passou a devolver em 24/11/2026) é bloqueio da API, não falta de
            # estoque: sobe o erro e o robô mantém o último preço e o link de afiliado como estavam.
            if e.code != 404:
                raise
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


PAUSA_PAGINA = 1.5  # segundos entre páginas do ML: devagar, como uma pessoa navegando


def preco_pagina(cat):
    """Reserva quando a API não dá preço (desde 24/11/2026 o ML não devolve mais o vendedor em destaque nem a
    lista de vendedores para apps). Abre o link de afiliado do próprio Matheus (meli.la -> página pública de
    afiliado, sem login) e lê o produto em destaque: "<nome> - R$ 1.824". Só aceita se o nome bater com o do
    catálogo. Devolve (info, situação) com situação 'ok', 'vazia' (página sem o produto) ou 'erro'."""
    from conferir_links import LIMITE, destaque, parecido
    try:
        titulo = destaque(cat["afiliado"])
    except Exception:
        return None, "erro"
    finally:
        time.sleep(PAUSA_PAGINA)
    titulo = titulo.replace("&quot;", '"').replace("&amp;", "&")
    m = re.search(r"R\$\s*([\d.]+)(?:,(\d{1,2}))?\s*$", titulo)
    if not titulo or "Perfil Social" in titulo or not m:
        return None, "vazia"
    if parecido(cat["nome"], titulo) < LIMITE and not cat.get("afiliado_ok"):
        return None, "vazia"
    preco = float(m.group(1).replace(".", "") + "." + (m.group(2) or "0"))
    return {"disponivel": True, "preco": preco, "fonte": "pagina"}, "ok"


def main():
    produtos = ler_json(ARQ_PRODUTOS)
    precos = ler_json(ARQ_PRECOS)
    try:
        token = token_ml()
    except urllib.error.HTTPError as e:
        print(f"AVISO: o Mercado Livre recusou o token ({e.code}); seguindo só com as páginas de afiliado. "
              "Refaça a autorização (LEIA-ME).", file=sys.stderr)
        token = None
    if not token:
        print("Sem a API do Mercado Livre: preços só pelas páginas de afiliado.")

    lidos, pela_pagina, marcar, desmarcar = 0, 0, set(), set()
    for pid, cat in produtos["produtos"].items():
        errado = cat.get("afiliado_errado")  # página do meli.la sem o produto: não ler preço por ele via API
        ref = (("item", cat["item"]) if cat.get("item") else None) or id_ml(cat.get("ml"))             or (None if errado else id_ml(precos.get(pid, {}).get("ml_resolvido")))
        info, nota = None, ""
        if ref and token:
            time.sleep(0.25)  # sem pressa: o ML derruba conexões quando as consultas vêm coladas
            try:
                info = (consulta_produto if ref[0] == "produto" else consulta_item)(ref[1], token)
            except urllib.error.HTTPError as e:
                nota = f" [API: erro {e.code}]"
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                nota = " [API: sem conexão]"
        if not (info and info.get("preco")) and cat.get("afiliado"):
            pag, situacao = preco_pagina(cat)
            if situacao == "ok":
                info = dict(info or {}, **pag)
                pela_pagina += 1
                if errado:
                    desmarcar.add(pid)
            elif situacao == "vazia" and not cat.get("afiliado_ok"):
                marcar.add(pid)  # o botão vai para a página do produto/busca até o vendedor voltar
        if not info:
            print(f"- {pid}: sem preço hoje, mantendo o último{nota}")
            continue
        lidos += 1
        if lidos % 50 == 0:  # salva o progresso de tempos em tempos
            gravar_json(ARQ_PRECOS, precos)
        reg = precos.setdefault(pid, {"historico": []})
        reg.update({k: v for k, v in info.items() if k not in ("preco", "fonte") and v is not None})
        reg["disponivel"] = info["disponivel"]
        reg["preco_original"] = info.get("preco_original")  # sem promoção hoje -> some a fitinha
        if info.get("fonte"):
            reg["fonte"] = info["fonte"]
        else:
            reg.pop("fonte", None)
        reg["atualizado"] = agora_iso()
        if info.get("preco"):
            # um ponto por dia: a leitura mais recente substitui a anterior do mesmo dia
            h = [x for x in reg["historico"] if x["data"] != hoje()]
            reg["historico"] = h + [{"data": hoje(), "preco": info["preco"]}]
        print(f"- {pid}: {'R$ %.2f' % info['preco'] if info.get('preco') else 'indisponível'}"
              + (" (página de afiliado)" if info.get("fonte") == "pagina" else "") + nota)

    gravar_json(ARQ_PRECOS, precos)
    if marcar or desmarcar:  # lê de novo antes de gravar: o hub também escreve nesse arquivo
        dados = ler_json(ARQ_PRODUTOS)
        for pid in marcar & set(dados["produtos"]):
            dados["produtos"][pid]["afiliado_errado"] = True
        for pid in desmarcar & set(dados["produtos"]):
            dados["produtos"][pid].pop("afiliado_errado", None)
        gravar_json(ARQ_PRODUTOS, dados)
    print(f"\n{lidos} de {len(produtos['produtos'])} produtos com preço hoje ({pela_pagina} pela página de afiliado). "
          f"Página sem o produto: {len(marcar)}; voltaram: {len(desmarcar)}.")
    if lidos == 0:
        print("ERRO: nenhum preço lido. Nada foi mudado no site.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
