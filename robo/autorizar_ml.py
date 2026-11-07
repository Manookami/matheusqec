"""Passo único: autoriza o robô a ler preços no Mercado Livre e mostra o refresh token para o GitHub.

Uso:  python robo/autorizar_ml.py
Antes: criar um app em https://developers.mercadolivre.com.br/devcenter com Redirect URI igual a REDIRECT abaixo.
"""
import json
from pathlib import Path
import urllib.parse
import urllib.request

REDIRECT = "https://matheusqec.com.br/"

cid = input("App ID (client_id): ").strip()
segredo = input("Chave secreta (client_secret): ").strip()
print("\n1) Abra este link, entre na sua conta e autorize:\n")
print("https://auth.mercadolivre.com.br/authorization?" + urllib.parse.urlencode(
    {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT}))
print("\n2) Você vai cair numa página com ?code=TG-... no endereço. Copie o endereço inteiro.")
url = input("\nCole aqui o endereço: ").strip()
code = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("code", [url])[0]

corpo = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": cid, "client_secret": segredo,
                                "code": code, "redirect_uri": REDIRECT}).encode()
req = urllib.request.Request("https://api.mercadolibre.com/oauth/token", data=corpo,
                             headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
resp = json.loads(urllib.request.urlopen(req, timeout=25).read())
# a chave fica só neste computador (pasta .segredos, fora do Git); nada vai para o GitHub
destino = Path(__file__).resolve().parent.parent / ".segredos" / "ml.json"
destino.parent.mkdir(exist_ok=True)
destino.write_text(json.dumps({"client_id": cid, "client_secret": segredo, "refresh_token": resp["refresh_token"]}, indent=1),
                   encoding="utf-8")
print(f"\nPronto! Chave salva em {destino} (só neste computador).")
print("Agora é só dar dois cliques em 'ATUALIZAR PRECOS.bat' sempre que quiser atualizar o site.")
