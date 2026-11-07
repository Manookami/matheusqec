"""Bot do canal: avisa quando um produto indicado nos vídeos baixa de preço.

Roda logo depois do robô de preços (GitHub Actions). Lê dados/precos.json, decide o que vale avisar e publica.
Provedor em bot_whatsapp/config.json:
  teste     -> só escreve a prévia em bot_whatsapp/saida/previa.txt (não publica nada)
  whapi     -> Canal do WhatsApp via Whapi.Cloud (WHAPI_TOKEN, WHATSAPP_CANAL_ID = "...@newsletter")
  telegram  -> canal do Telegram (TELEGRAM_TOKEN, TELEGRAM_CANAL = "@seucanal")
Uso: python bot_whatsapp/bot.py [--provedor teste]
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "robo"))
from comum import ARQ_PRECOS, ARQ_PRODUTOS, DADOS, gravar_json, ler_json, link_produto, quedas, reais  # noqa: E402

ARQ_ENVIADOS = DADOS / "alertas_enviados.json"


def escolher(dados, precos, cfg, enviados):
    """Quedas que merecem alerta, sem repetir o mesmo produto toda hora."""
    hoje = date.today()
    novos = []
    for q in quedas(dados, precos, cfg["queda_minima"], cfg["janela_dias"]):
        ult = enviados.get(q["produto"])
        if ult:
            caiu_mais = q["agora"] <= ult["preco"] * (1 - cfg["nova_queda_minima"])
            pausa_ok = date.fromisoformat(ult["data"]) <= hoje - timedelta(days=cfg["pausa_dias_mesmo_produto"])
            if not (caiu_mais or (pausa_ok and q["agora"] < ult["preco"])):
                continue
        novos.append(q)
    # menor preço da história primeiro, depois as maiores quedas
    novos.sort(key=lambda q: (not q["menor_da_historia"], -q["queda"]))
    return novos[: cfg["max_alertas_por_vez"]]


def pagina_do_produto(pid, dados):
    for pg in dados["paginas"]:
        if pg["escolha"]["produto"] == pid or any(a["produto"] == pid for a in pg.get("alternativas", [])):
            return pg
    return None


def mensagem(q, dados, precos):
    prod = dados["produtos"][q["produto"]]
    pg = pagina_do_produto(q["produto"], dados)
    linhas = [
        f"🔥 *PREÇO CAIU* · {prod['nome']}",
        "",
        f"De ~{reais(q['antes'])}~ por *{reais(q['agora'])}* (−{q['queda']:.0%})",
    ]
    if q["menor_da_historia"]:
        linhas.append("🏆 *Menor preço que eu já vi nesse produto!*")
    if pg:
        if pg["escolha"]["produto"] == q["produto"]:
            linhas += ["", f"Foi a minha escolha em \"{pg['titulo']}\"."]
        else:
            alt = next(a for a in pg["alternativas"] if a["produto"] == q["produto"])
            linhas += ["", f"Indiquei no vídeo \"{pg['titulo']}\" → {alt['para']}."]
    linhas += ["", f"👉 {link_produto(q['produto'], dados, precos)}"]
    if pg:
        linhas.append(f"📋 Minha análise: {dados['site']['url'].rstrip('/')}/{pg['slug']}/")
    linhas += ["", "_Preço pode mudar a qualquer momento. Link de afiliado._"]
    return "\n".join(linhas), precos.get(q["produto"], {}).get("imagem")


def post(url, corpo, token=None):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"{}")


def enviar_whapi(texto, imagem):
    token, canal = os.environ["WHAPI_TOKEN"], os.environ["WHATSAPP_CANAL_ID"]
    if imagem:
        post("https://gate.whapi.cloud/messages/image", {"to": canal, "media": imagem, "caption": texto}, token)
    else:
        post("https://gate.whapi.cloud/messages/text", {"to": canal, "body": texto}, token)


def enviar_telegram(texto, imagem):
    token, canal = os.environ["TELEGRAM_TOKEN"], os.environ["TELEGRAM_CANAL"]
    html = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = re.sub(r"\*(.+?)\*", r"<b>\1</b>", html)
    html = re.sub(r"~(.+?)~", r"<s>\1</s>", html)
    html = re.sub(r"(?m)^_(.+)_$", r"<i>\1</i>", html)
    base = f"https://api.telegram.org/bot{token}"
    if imagem:
        post(base + "/sendPhoto", {"chat_id": canal, "photo": imagem, "caption": html, "parse_mode": "HTML"})
    else:
        post(base + "/sendMessage", {"chat_id": canal, "text": html, "parse_mode": "HTML"})


def main():
    cfg = ler_json(AQUI / "config.json")
    if "--provedor" in sys.argv:
        cfg["provedor"] = sys.argv[sys.argv.index("--provedor") + 1]
    dados, precos = ler_json(ARQ_PRODUTOS), ler_json(ARQ_PRECOS)
    enviados = ler_json(ARQ_ENVIADOS)

    hora = datetime.now().hour
    if not cfg["horario"][0] <= hora < cfg["horario"][1] and cfg["provedor"] != "teste":
        print(f"Fora do horário de postar ({hora}h). Nada enviado.")
        return 0

    alertas = escolher(dados, precos, cfg, enviados)
    if not alertas:
        print("Nenhuma queda nova pra avisar.")
        return 0

    saida = AQUI / "saida"
    saida.mkdir(exist_ok=True)
    for q in alertas:
        texto, imagem = mensagem(q, dados, precos)
        if cfg["provedor"] == "teste":
            with open(saida / "previa.txt", "a", encoding="utf-8") as f:
                f.write(f"===== {datetime.now():%d/%m %H:%M} · imagem: {imagem or '-'}\n{texto}\n\n")
            print(texto, "\n")
            continue
        try:
            (enviar_whapi if cfg["provedor"] == "whapi" else enviar_telegram)(texto, imagem)
        except Exception as ex:
            print(f"ERRO ao publicar {q['produto']}: {ex}", file=sys.stderr)
            continue
        enviados[q["produto"]] = {"preco": q["agora"], "data": date.today().isoformat()}
        print(f"publicado: {q['produto']} {reais(q['agora'])}")

    if cfg["provedor"] != "teste":
        gravar_json(ARQ_ENVIADOS, enviados)
    return 0


if __name__ == "__main__":
    sys.exit(main())
