# matheusqec.com.br — site do canal "Qual Eu Compro?"

Vitrine com ~670 produtos (celulares, TVs, notebooks, tablets, vestíveis, videogames e achados gerais). Cada botão
**Comprar** abre o link de afiliado (meli.la) do Matheus. O site não tem cadastro e não guarda dado de ninguém.

## Como os preços se atualizam (segurança)

O robô roda **no computador do Matheus**, não no servidor:

1. dois cliques em **`ATUALIZAR PRECOS.bat`** (ou `python robo/rodar_local.py`);
2. ele consulta os preços pela **API oficial do Mercado Livre** com a chave que fica em `.segredos/ml.json`
   (pasta fora do Git: nunca vai para o GitHub nem para o site);
3. roda os testes, gera o site e envia **só a lista de preços** para o GitHub;
4. o GitHub publica o site (`.github/workflows/diario.yml`), sem nenhuma senha ou chave guardada lá.

Se alguém invadir o site ou o GitHub, não acha acesso nenhum à conta do Mercado Livre.

**Agendado:** o Agendador de Tarefas do Windows roda `robo/agendado.bat` **todo dia às 12h** (tarefa "Qual Eu Compro -
precos"; se o PC estiver desligado, roda quando ligar). O resultado da última rodada fica em `robo/ultimo_log.txt`.

**Limite da API:** produtos de catálogo (`/p/MLB...`) são lidos pela API. Anúncios fora do catálogo (`/up/...`, ~50)
o ML não deixa ler: o site mostra o último preço por até **3 dias** e depois troca por "Ver preço no Mercado Livre".

## Fitinha de desconto (regras anti-desconto-falso)

`desconto_real` em `robo/comum.py`: só aparece se o preço de hoje estiver **5% ou mais abaixo da mediana dos últimos
30 dias** do nosso próprio histórico, com **7+ dias e 3+ leituras**. Queda acima de **60%** é tratada como anúncio
suspeito (sem fitinha). O "de R$ X por R$ Y" dos anúncios do ML é ignorado.

Produtos entram no catálogo só se o anúncio tiver **50+ vendas** (ou for loja oficial) e nota 4+.

## Quando sai vídeo novo

O Claude adiciona em `dados/produtos.json` os produtos do vídeo (`afiliado` = link meli.la, `videos` = id do vídeo)
e o vídeo em `videos`. Produtos com vídeo ganham a ⭐ "Recomendação do canal".

## Configuração (uma vez só)

| # | O quê | Onde |
|---|---|---|
| 1 | Registrar **matheusqec.com.br** | registro.br |
| 2 | Criar conta no GitHub; o Claude cria o repositório, envia o site e liga o domínio | github.com |
| 3 | Criar o app de desenvolvedor no ML (Redirect URI `https://matheusqec.com.br/`) e rodar `python robo/autorizar_ml.py` (salva a chave em `.segredos/`) | developers.mercadolivre.com.br |

## Testar no computador

```
python site/servir.py                     # site em http://localhost:8010 (sem cache)
python testes/teste.py                    # testes com dados simulados (também rodam antes de publicar)
python site/build.py                      # gera site/dist
```

## Motion de divulgação

`motion/index.html` (animação controlada pelo tempo, com "câmera" de zoom/pan) + `node motion/gravar.js`
→ `motion/motion_site.mp4` (1080p, 60 fps, 21,5 s) e `motion/eventos.json` (tempos dos sons).
`python motion/audio.py` monta a trilha (música lo-fi do canal + pops, teclas, clique, ding e whooshes, -16 LUFS)
→ `motion/motion_site_com_som.mp4`. `node motion/gravar.js previa 5 12` gera só alguns quadros para conferir.
