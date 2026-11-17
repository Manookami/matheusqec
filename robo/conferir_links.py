"""Confere se cada link de afiliado (meli.la) leva ao produto certo.

O meli.la abre a página de afiliado do Matheus no ML com o produto em destaque. Se o link foi gerado para o
anúncio errado (ou o anúncio acabou), a página abre sem o produto e a pessoa não acha o que clicou.
Este script abre cada link (sem login, 1 por segundo), lê o título do produto em destaque (og:title) e compara
com o nome do produto no catálogo. Resultado em robo/links_conferidos.json.

Link errado (parecido < 0.45) ganha `afiliado_errado: true` no produtos.json: o site então manda o clique para a
página do produto no ML com a tag de afiliado (comum.link_produto). A marca só sai quando o link é trocado e o
novo passa na conferência. `afiliado_ok: true` num produto = conferido à mão, nunca marcar.

uso: python robo/conferir_links.py [--so-novos]   (--so-novos: só links que ainda não foram conferidos)
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
        if not url or ("--so-novos" in sys.argv and feitos.get(pid, {}).get("url") == url):
            continue
        try:
            titulo = destaque(url)
        except Exception as e:  # sem internet etc.: confere da próxima vez
            print(f"- {pid}: erro {e}")
            continue
        nota = parecido(p["nome"], titulo) if titulo and "Perfil Social" not in titulo else 0.0
        novo_link = feitos.get(pid, {}).get("url") != url
        feitos[pid] = {"url": url, "titulo": titulo, "parecido": round(nota, 2)}
        if nota < LIMITE and not p.get("afiliado_ok"):
            marcar.add(pid)
        elif novo_link:
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
    print(f"Links conferidos. Errados: {len(marcar)}" + (f" -> {sorted(marcar)}" if marcar else ""))


if __name__ == "__main__":
    main()
