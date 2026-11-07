"""Testes do site e do bot com dados simulados (não toca em dados/ de verdade).

Uso: python testes/teste.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="qec_"))
os.environ["QEC_DADOS"] = str(TMP / "dados")
os.environ["QEC_DIST"] = str(TMP / "dist")
os.environ["PYTHONIOENCODING"] = "utf-8"
(TMP / "dados").mkdir()
sys.path.insert(0, str(RAIZ / "robo"))
sys.path.insert(0, str(RAIZ / "bot_whatsapp"))

import comum  # noqa: E402
import bot  # noqa: E402

falhas = []


def confere(cond, desc):
    print(("  ok   " if cond else "  FALHOU ") + desc)
    if not cond:
        falhas.append(desc)


def dia(n):
    return (date.today() - timedelta(days=n)).isoformat()


AFI = "https://meli.la/TESTE123"
produtos = json.loads((RAIZ / "dados" / "produtos.json").read_text(encoding="utf-8"))
produtos["afiliado"] = {"matt_word": "matheusqec", "matt_tool": "123"}
produtos["produtos"]["galaxy-a57"]["afiliado"] = AFI
produtos["produtos"]["poco-x8-pro"]["afiliado"] = ""  # simula produto ainda sem link de afiliado
CFG = json.loads((RAIZ / "bot_whatsapp" / "config.json").read_text(encoding="utf-8"))


def cenario(precos, enviados=None):
    comum.gravar_json(comum.ARQ_PRODUTOS, produtos)
    comum.gravar_json(comum.ARQ_PRECOS, precos)
    return bot.escolher(produtos, precos, CFG, enviados or {})


print("\n1) Links")
confere(comum.link_produto("galaxy-a57", produtos, {}) == AFI, "produto com link de afiliado -> vai direto pro link do Matheus")
l = comum.link_produto("poco-x8-pro", produtos, {})
confere("lista.mercadolivre.com.br/poco-x8-pro" in l and "matt_word=matheusqec" in l, "sem link -> busca do ML com tag de afiliado")
l = comum.link_produto("galaxy-a57", produtos, {"galaxy-a57": {"disponivel": False}})
confere(l != AFI and "matt_word" in l, "esgotado -> troca pra busca com tag")
confere(comum.id_ml("https://www.mercadolivre.com.br/samsung-a57/p/MLB12345678") == ("produto", "MLB12345678"), "lê código de catálogo /p/")
confere(comum.id_ml("https://produto.mercadolivre.com.br/MLB-4012345678-samsung") == ("item", "MLB4012345678"), "lê código de anúncio")
confere(comum.reais(1749) == "R$ 1.749" and comum.reais(1749.9) == "R$ 1.749,90", "formato de reais")

print("\n2) Bot: quando avisar")
base = {"historico": [{"data": dia(5), "preco": 1749}, {"data": dia(0), "preco": 1749}], "disponivel": True}
confere(cenario({"galaxy-a57": base}) == [], "preço parado -> não avisa")
caiu = {"historico": [{"data": dia(5), "preco": 1749}, {"data": dia(0), "preco": 1599}], "disponivel": True}
r = cenario({"galaxy-a57": caiu})
confere(len(r) == 1 and r[0]["produto"] == "galaxy-a57", "caiu 8,6% -> avisa")
pouco = {"historico": [{"data": dia(5), "preco": 1749}, {"data": dia(0), "preco": 1700}], "disponivel": True}
confere(cenario({"galaxy-a57": pouco}) == [], "caiu só 2,8% -> não avisa")
velho = {"historico": [{"data": dia(20), "preco": 1999}, {"data": dia(0), "preco": 1599}], "disponivel": True}
confere(cenario({"poco-x8-pro": velho}) == [], "queda fora da janela de 7 dias -> não avisa")
env = {"galaxy-a57": {"preco": 1599, "data": dia(1)}}
confere(cenario({"galaxy-a57": caiu}, env) == [], "já avisado ontem no mesmo preço -> não repete")
mais = {"historico": [{"data": dia(5), "preco": 1749}, {"data": dia(0), "preco": 1499}], "disponivel": True}
confere(len(cenario({"galaxy-a57": mais}, env)) == 1, "caiu mais 6% desde o último aviso -> avisa de novo")
r = cenario({"redmi-note-15-pro": {"historico": [{"data": dia(3), "preco": 1899}, {"data": dia(0), "preco": 1699}]}})
confere(len(r) == 1 and not r[0]["menor_da_historia"], "histórico curto -> não diz 'menor da história'")
recorde = {"historico": [{"data": dia(5), "preco": 1749}, {"data": dia(0), "preco": 1399}], "disponivel": True}
r = cenario({"galaxy-a57": recorde})
confere(r[0]["menor_da_historia"], "A57 abaixo de R$ 1.457 com histórico do vídeo -> 'menor da história'")
confere(not cenario({"galaxy-a57": mais})[0]["menor_da_historia"], "R$ 1.499 não bate o recorde de R$ 1.457 -> não diz 'menor'")
esgot = dict(caiu, disponivel=False)
confere(cenario({"galaxy-a57": esgot}) == [], "esgotado -> não avisa")
muitos = {pid: {"historico": [{"data": dia(5), "preco": 2000}, {"data": dia(0), "preco": 1500}], "disponivel": True}
          for pid in produtos["produtos"]}
confere(len(cenario(muitos)) == CFG["max_alertas_por_vez"], f"5 quedas ao mesmo tempo -> só {CFG['max_alertas_por_vez']} alertas")

print("\n3) Bot: mensagem")
cenario({"galaxy-a57": mais})
txt, _ = bot.mensagem(bot.escolher(produtos, {"galaxy-a57": mais}, CFG, {})[0], produtos, {"galaxy-a57": mais})
print("     " + txt.replace("\n", "\n     "))
confere(AFI in txt, "mensagem usa o link de afiliado")
confere("R$ 1.749" in txt and "R$ 1.499" in txt and "−14%" in txt, "mensagem mostra de/por e porcentagem")
confere(len(txt) < 700, "mensagem curta (< 700 caracteres)")

print("\n4) Site")
comum.gravar_json(comum.ARQ_PRECOS, {"galaxy-a57": mais})
out = subprocess.run([sys.executable, str(RAIZ / "site" / "build.py")], capture_output=True, text=True, encoding="utf-8")
confere(out.returncode == 0, "build sem erro" + ("" if out.returncode == 0 else ": " + out.stderr[-300:]))
dist = TMP / "dist"
red = (dist / "a57" / "index.html").read_text(encoding="utf-8")
confere(f'content="0;url={AFI}"' in red and f'location.replace("{AFI}")' in red, "/a57 redireciona pro link de afiliado")
confere((dist / "ir" / "galaxy-a57" / "index.html").exists(), "/ir/galaxy-a57 também existe")
confere('noindex' in red, "página de redirecionamento fora do Google")
pg = (dist / "melhor-celular-ate-2000" / "index.html").read_text(encoding="utf-8")
confere(pg.count(AFI) >= 1, "página do vídeo tem botão com link de afiliado")
confere("R$ 1.499" in pg, "página mostra preço de hoje")
confere('rel="sponsored nofollow noopener"' in pg, "links de afiliado marcados como patrocinados")

print("\n5) Desconto de verdade (fitinha)")


def serie(*trechos):
    """serie((dias_atras_inicio, dias_atras_fim, preço), ...) -> histórico diário."""
    h = {}
    for ini, fim, preco in trechos:
        for d in range(ini, fim - 1, -1):
            h[dia(d)] = preco
    return {"historico": [{"data": k, "preco": v} for k, v in sorted(h.items())], "disponivel": True}


def desconto_de(reg, pid="poco-x8-pro"):
    return (comum.resumo_preco(pid, produtos, {pid: reg}) or {}).get("desconto", 0)


parado = dict(serie((40, 0, 2422)), preco_original=4999)
confere(desconto_de(parado) == 0, "preço parado há 40 dias com 'de R$ 4.999' do ML -> sem desconto")
caiu_mesmo = serie((25, 1, 2400), (0, 0, 1999))
confere(desconto_de(caiu_mesmo) == 17, "R$ 2.400 por 25 dias e hoje R$ 1.999 -> 17% de desconto real")
truque = serie((25, 3, 2000), (2, 1, 2600), (0, 0, 2000))
confere(desconto_de(truque) == 0, "sobe pra R$ 2.600 e 'baixa' pra R$ 2.000 de novo -> não é desconto")
curto = serie((3, 1, 2400), (0, 0, 1999))
confere(desconto_de(curto) == 0, "só 3 dias de histórico -> ainda não afirma desconto")
dois = {"historico": [{"data": dia(10), "preco": 684}, {"data": dia(0), "preco": 387}], "disponivel": True}
confere(desconto_de(dois) == 0, "só 2 leituras (684 -> 387) -> não afirma desconto")
velho_preco = comum.resumo_preco("poco-x8-pro", produtos, {"poco-x8-pro": serie((10, 5, 2400))})
confere(velho_preco and not velho_preco["recente"], "último preço de 5 dias atrás -> não é mais 'recente' (site mostra 'Ver preço')")
golpe = serie((25, 1, 2400), (0, 0, 699))
confere(desconto_de(golpe) == 0, "caiu 71% de um dia pro outro -> suspeito, sem fitinha")
pouco = serie((20, 1, 2400), (0, 0, 2340))
confere(desconto_de(pouco) == 0, "caiu só 2,5% -> sem fitinha")
um_dia = serie((20, 1, 1300), (0, 0, 607))
confere(desconto_de(um_dia) == 0, "caiu 53% num dia só (DualSense Edge a R$ 607) -> espera confirmar, sem fitinha")
confirmado = serie((20, 2, 1300), (1, 0, 800))
confere(desconto_de(confirmado) == 38, "caiu 38% e ficou assim 2 dias seguidos -> fitinha 38%")

comum.gravar_json(comum.ARQ_PRECOS, {"poco-x8-pro": caiu_mesmo, "galaxy-a57": dict(serie((30, 0, 1899)), preco_original=3799)})
subprocess.run([sys.executable, str(RAIZ / "site" / "build.py")], capture_output=True)
home = (dist / "index.html").read_text(encoding="utf-8")
fitas = re.findall(r'<span class="fita">([^<]*)</span>', home)
confere(fitas and set(fitas) == {"17% OFF"}, f"site: só o produto que caiu de verdade ganha fitinha ({fitas[:3]})")
confere("50% OFF" not in home, "o '50% OFF' do anúncio do ML não aparece no site")
busca = (dist / "busca" / "index.html").read_text(encoding="utf-8")
confere(busca.count('class="card"') == len(produtos["produtos"]), f"página de busca tem todos os {len(produtos['produtos'])} produtos")
confere(home.count('class="card"') < len(produtos["produtos"]), "página inicial mostra só uma vitrine de cada categoria")
confere(all((dist / c["id"] / "index.html").exists() for c in produtos["categorias"]), "uma página por categoria")
confere('class="carrossel"' in home and home.count('class="slide ') >= 2, "página inicial tem carrossel com vários banners")
confere(produtos["site"]["descricao"] in home, "banner principal mostra a descrição do canal")
cat = (dist / "celulares" / "index.html").read_text(encoding="utf-8")
confere('name="faixa"' in cat and 'data-ordem="menor"' in cat, "categoria tem filtro de preço e ordenação")

# todo link interno aponta para algo que existe
quebrados = []
for html in dist.rglob("*.html"):
    for href in re.findall(r'(?:href|src)="(/[^"#?]*)', html.read_text(encoding="utf-8")):
        alvo = dist / href.lstrip("/")
        if not (alvo.is_file() or (alvo / "index.html").is_file()):
            quebrados.append(f"{html.relative_to(dist)} -> {href}")
confere(not quebrados, "nenhum link interno quebrado" + (": " + ", ".join(quebrados[:5]) if quebrados else ""))

produtos["produtos"]["moto-g86"]["atalho"] = "a57"
comum.gravar_json(comum.ARQ_PRODUTOS, produtos)
out = subprocess.run([sys.executable, str(RAIZ / "site" / "build.py")], capture_output=True, text=True, encoding="utf-8")
confere(out.returncode != 0 and "repetido" in (out.stdout + out.stderr), "atalho repetido -> build avisa e para")

shutil.rmtree(TMP, ignore_errors=True)
print(f"\n{'TUDO CERTO' if not falhas else f'{len(falhas)} FALHA(S)'}")
sys.exit(1 if falhas else 0)
