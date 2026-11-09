"""Robô de preços que roda NO COMPUTADOR DO MATHEUS (nada de senha/chave no GitHub nem no site).

O que faz, em ordem:
  1. lê a chave do app do Mercado Livre de  .segredos/ml.json  (pasta fora do Git, só existe neste PC);
  2. consulta os preços pela API oficial do ML (robo/atualiza_precos.py) e guarda a chave renovada;
  3. roda os testes e gera o site (site/dist);
  4. se a pasta estiver ligada ao GitHub, envia SÓ os dados novos (git commit + push) -> o site atualiza sozinho.

Uso: dar dois cliques em  ATUALIZAR PRECOS.bat  (ou: python robo/rodar_local.py)
Primeira vez: python robo/autorizar_ml.py  e salvar o resultado em .segredos/ml.json (o script explica).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEGREDOS = RAIZ / ".segredos" / "ml.json"
ULTIMA = RAIZ / "robo" / "ultima_rodada.txt"  # data da última rodada completa (fora do Git)


def passo(msg):
    print(f"\n=== {msg}")


def roda(*cmd, env=None):
    r = subprocess.run(cmd, cwd=RAIZ, env=env)
    if r.returncode:
        sys.exit(f"Parou: '{' '.join(cmd)}' deu erro (código {r.returncode}). Nada foi enviado ao site.")


def main():
    hoje = __import__("datetime").date.today().isoformat()
    if "--agendado" in sys.argv and ULTIMA.exists() and ULTIMA.read_text().strip() == hoje:
        print("Os preços já foram atualizados hoje: nada a fazer.")
        return
    if not SEGREDOS.exists():
        sys.exit(f"Falta a chave do Mercado Livre em {SEGREDOS}.\n"
                 "Rode 'python robo/autorizar_ml.py' uma vez e salve client_id, client_secret e refresh_token nesse arquivo:\n"
                 '{"client_id": "...", "client_secret": "...", "refresh_token": "..."}')
    chave = json.loads(SEGREDOS.read_text(encoding="utf-8"))

    passo("1/4 Consultando preços na API oficial do Mercado Livre")
    novo = Path(tempfile.gettempdir()) / "qec_refresh.txt"
    novo.unlink(missing_ok=True)
    env = dict(os.environ, ML_CLIENT_ID=chave["client_id"], ML_CLIENT_SECRET=chave["client_secret"],
               ML_REFRESH_TOKEN=chave["refresh_token"], ML_NOVO_REFRESH_ARQ=str(novo), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "robo/atualiza_precos.py"], cwd=RAIZ, env=env)
    if novo.exists() and novo.read_text().strip():  # o ML troca a chave a cada uso: guarda a nova
        chave["refresh_token"] = novo.read_text().strip()
        SEGREDOS.write_text(json.dumps(chave, indent=1), encoding="utf-8")
        novo.unlink()
    if r.returncode:
        sys.exit("Parou: o robô de preços deu erro (veja as mensagens acima). Nada foi enviado ao site.\n"
                 "Se a mensagem disser que o Mercado Livre recusou o token, rode de novo 'python robo/autorizar_ml.py'.")

    passo("2/4 Testes")
    roda(sys.executable, "testes/teste.py")

    passo("3/4 Gerando o site")
    roda(sys.executable, "site/build.py")

    passo("4/4 Enviando para o GitHub")
    if not (RAIZ / ".git").exists():
        print("Esta pasta ainda não está ligada ao GitHub: preços atualizados só aqui no computador.")
        ULTIMA.write_text(hoje)
        return
    ULTIMA.write_text(hoje)
    roda("git", "add", "dados/")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=RAIZ).returncode == 0:
        print("Nenhum preço mudou. Nada para enviar.")
        return
    roda("git", "commit", "-m", "preços atualizados")
    roda("git", "push")
    print("Enviado! O site atualiza em 1 ou 2 minutos.")


if __name__ == "__main__":
    main()
