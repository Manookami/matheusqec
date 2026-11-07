"""Passo único: autoriza o robô a ler preços no Mercado Livre e guarda a chave só neste computador (.segredos/ml.json).

Uso:  python robo/autorizar_ml.py
Antes: criar um app em https://developers.mercadolivre.com.br/devcenter com Redirect URI igual a REDIRECT abaixo.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REDIRECT = "https://matheusqec.com.br/"
DESTINO = Path(__file__).resolve().parent.parent / ".segredos" / "ml.json"


def limpo(txt):
    return re.sub(r"[^A-Za-z0-9_\-]", "", txt)  # tira espaços e caracteres invisíveis que vêm no Ctrl+V


cid = limpo(input("App ID (client_id): "))
segredo = limpo(input("Chave secreta (client_secret): "))
print("\n" * 40)  # empurra a chave secreta para fora da tela
print(f"App ID {cid} | chave secreta com {len(segredo)} caracteres (deve ter 32)")

while True:
    print("\n1) Abra este link no navegador onde o Mercado Livre está logado e autorize:\n")
    print("https://auth.mercadolivre.com.br/authorization?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT}))
    print("\n2) A página seguinte não abre (normal). Copie o endereço da barra: https://matheusqec.com.br/?code=TG-...")
    code = ""
    while not code.startswith("TG-"):  # Enter vazio ou endereço sem código: pergunta de novo
        url = input("\nCole aqui o endereço: ").strip()
        code = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("code", [url])[0].strip()

    corpo = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": cid, "client_secret": segredo,
                                    "code": code, "redirect_uri": REDIRECT}).encode()
    req = urllib.request.Request("https://api.mercadolibre.com/oauth/token", data=corpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=25).read())
        break
    except urllib.error.HTTPError as e:
        erro = e.read().decode("utf-8", "replace")
        print(f"\nO Mercado Livre recusou ({e.code}): {erro}")
        if "client" in erro.lower() and "secret" in erro.lower() or "invalid_client" in erro:
            print("-> A chave secreta ou o App ID estão errados. Feche (Ctrl+C) e rode de novo conferindo os dois.")
        else:
            print("-> Provavelmente o código venceu ou já foi usado. Vamos gerar outro:")

# a chave fica só neste computador (pasta .segredos, fora do Git); nada vai para o GitHub
DESTINO.parent.mkdir(exist_ok=True)
DESTINO.write_text(json.dumps({"client_id": cid, "client_secret": segredo, "refresh_token": resp["refresh_token"]}, indent=1),
                   encoding="utf-8")
print(f"\nPronto! Chave salva em {DESTINO} (só neste computador).")
print("Agora é só dar dois cliques em 'ATUALIZAR PRECOS.bat' sempre que quiser atualizar o site.")
