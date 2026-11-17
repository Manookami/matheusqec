"""Confere se cada link de afiliado (meli.la) leva ao produto certo.

O meli.la abre a página de afiliado do Matheus no ML com o produto em destaque. Se o link foi gerado para o
anúncio errado (ou o anúncio acabou), a página abre sem o produto e a pessoa não acha o que clicou.
Este script abre cada link (sem login, 1 por segundo), lê o título do produto em destaque (og:title) e compara
com o nome do produto no catálogo. Resultado em robo/links_conferidos.json.

Por que quebra: o meli.la aponta para a página de CATÁLOGO do produto. Quando ela fica sem vendedor principal
(acabou o estoque, vendedor saiu), o ML mostra "Este perfil ainda está vazio". Quando volta a ter vendedor, o
mesmo link volta a funcionar. Então:
  - não abriu o produto (parecido < 0.45) -> `afiliado_errado: true`: o site manda o clique para a página do
    produto no ML (ou para a busca, se esgotado), sempre com a tag de afiliado (comum.link_produto);
  - voltou a abrir o produto -> a marca sai sozinha e o site volta a usar o meli.la.
`afiliado_ok: true` num produto = conferido à mão, nunca marcar.

uso: python robo/conferir_links.py           links novos + os que estão marcados como errados (rápido, todo dia)
     python robo/conferir_links.py --todos   todos os links (~30 min, às segundas)
"""
import json
import re
import sys
import time
import unicodedata
import urllib.request

from comum import ARQ_PRODUTOS, RAIZ, gravar_json, ler_json

SAIDA = RAIZ / "robo" / "links_conferidos.json"
LIMITE = 0.45
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
GENERICAS = {"de", "da", "do", "com", "para", "e", "cor", "sem", "fio", "o", "a", "em", "gb", "tela", "polegadas",
             "smartphone", "celular", "notebook", "smart", "tv", "tablet", "fone", "ouvido", "controle", "console",
             "preto", "branco", "cinza", "azul", "ram", "ssd", "wi", "fi", "5g", "4g", "dual", "sim"}


def palavras(txt):
    txt = unicodedata.normalize("NFKD", txt.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", txt) if w not in GENERICAS and len(w) > 1}


def destaque(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "ignore")
    m = re.search(r'og:title" content="([^"]*)"', html)
    return m.group(1) if m else ""


def parecido(nome, titulo):
    """Fração das palavras importantes do nome do catálogo que aparecem no título do destaque."""
    a, b = palavras(nome), palavras(titulo)
    return len(a & b) / max(1, len(a))


def main():
    produtos = ler_json(ARQ_PRODUTOS)["produtos"]
    feitos = ler_json(SAIDA, {}) or {}
    marcar, desmarcar = set(), set()
    for i, (pid, p) in enumerate(produtos.items()):
        url = p.get("afiliado")
        ja_visto = feitos.get(pid, {}).get("url") == url
        if not url or ("--todos" not in sys.argv and ja_visto and not p.get("afiliado_errado")):
            continue
        try:
            titulo = destaque(url)
        except Exception as e:  # sem internet etc.: confere da próxima vez
            print(f"- {pid}: erro {e}")
            continue
        nota = parecido(p["nome"], titulo) if titulo and "Perfil Social" not in titulo else 0.0
        feitos[pid] = {"url": url, "titulo": titulo, "parecido": round(nota, 2)}
        if nota < LIMITE and not p.get("afiliado_ok"):
            marcar.add(pid)
        elif p.get("afiliado_errado"):
            desmarcar.add(pid)
        print(f"{i:4} {nota:.2f} {pid[:40]:40} -> {titulo[:70]}")
        if i % 25 == 0:
            SAIDA.write_text(json.dumps(feitos, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(1)
    SAIDA.write_text(json.dumps(feitos, ensure_ascii=False, indent=1), encoding="utf-8")
    if marcar or desmarcar:  # lê de novo antes de gravar: o hub também escreve nesse arquivo
        dados = ler_json(ARQ_PRODUTOS)
        for pid in marcar & set(dados["produtos"]):
            dados["produtos"][pid]["afiliado_errado"] = True
        for pid in desmarcar & set(dados["produtos"]):
            dados["produtos"][pid].pop("afiliado_errado", None)
        gravar_json(ARQ_PRODUTOS, dados)
    print(f"Links conferidos. Sem o produto na página: {len(marcar)}. Voltaram a funcionar: {len(desmarcar)}"
          + (f" -> {sorted(desmarcar)}" if desmarcar else ""))


if __name__ == "__main__":
    main()
