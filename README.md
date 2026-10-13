<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/duda-logo-escuro.svg">
  <img src="assets/duda-logo-claro.svg" alt="Duda, agente de atendimento" width="460">
</picture>

<br><br>

Um agente de atendimento no WhatsApp que **conversa como gente**: espera o cliente terminar de falar, mostra "digitando", responde em mensagens curtas e lembra de quem já falou com ele.

![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![PydanticAI](https://img.shields.io/badge/PydanticAI-agente-E92063)
![WAHA](https://img.shields.io/badge/WAHA-WhatsApp-25D366?logo=whatsapp&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-WAHA-2496ED?logo=docker&logoColor=white)

**Projeto do curso 2 · Seu Agente Ligado 24h**

</div>

---

## O que ele faz

- 💬 **Ritmo de gente:** junta as mensagens picadas, marca como lida, mostra "digitando" e responde no tempo de quem escreve.
- ✂️ **Mensagens curtas:** divide a resposta em até três mensagens, sem markdown.
- 🧠 **Memória:** lembra de cada contato, mesmo depois de reiniciar.
- 🎙️ **Áudio, foto e PDF:** entende o que o cliente mandou e responde como quem ouviu, viu e leu.
- 🛡️ **Sabe o que não sabe:** responde só com o que está no prompt e diz que vai confirmar o resto.
- 📅 **Sabe que dia é hoje:** entende "amanhã" e "sábado que vem".

## Como funciona

Todo agente tem três peças. Aqui elas ficam assim:

| Peça | O que faz | Onde está |
| --- | --- | --- |
| **Canal** | leva a mensagem do WhatsApp até o código e a resposta de volta | [WAHA](https://waha.devlike.pro) + `app/whatsapp.py` e `app/main.py` |
| **Código** | buffer, ritmo, memória e mídia | `app/ritmo.py`, `app/memory.py` e `app/midia.py` |
| **LLM** | personalidade, tom e conhecimento da empresa | [PydanticAI](https://ai.pydantic.dev) + `prompts/system_prompt.md` |

## Começando

Precisa de Python 3.11 ou mais novo, [Docker](https://www.docker.com/products/docker-desktop/) e uma chave da [OpenRouter](https://openrouter.ai/settings/keys).

```bash
# 1. dependências
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. configuração: copia o exemplo e preenche os valores
cp .env.example .env

# 3. WhatsApp: sobe o WAHA, abre localhost:3000/dashboard e lê o QR code
docker compose up -d

# 4. agente
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Pra conversar com o agente só no terminal, sem WhatsApp: `python chat.py`.

> ⚠️ Use um **número de teste**, nunca o teu pessoal nem o da empresa.
>
> 💻 No Mac com chip Apple, o `docker-compose.yml` já usa a imagem `devlikeapro/waha:arm`.

## Rodando na VPS

Pra deixar a Duda no ar 24 horas, numa VPS com [Docker](https://docs.docker.com/engine/install/):

1. **Domínios:** aponta dois subdomínios pro IP da VPS, por exemplo `bot.teudominio.com.br` (a Duda) e `waha.teudominio.com.br` (o painel do WAHA).
2. **`.env` preenchido** na VPS: as chaves de sempre, mais `DOMINIO`, `DOMINIO_WAHA` e `WHATSAPP_HOOK_HMAC_KEY` (uma chave longa, `openssl rand -hex 32`), com `WAHA_URL=http://waha:3000`.
3. **Copia o projeto** pra VPS, sem o `.env` do teu computador nem o `historico/`.
4. **Sobe tudo:**

```bash
docker compose -f docker-compose.vps.yml up -d --build
```

O Caddy gera o HTTPS sozinho. Depois é só abrir `https://waha.teudominio.com.br/dashboard`, entrar com o usuário e a senha do `.env` e ler o QR code. O webhook só aceita chamadas assinadas pelo teu WAHA. O passo a passo pra atualizar a VPS está no `CLAUDE.example.md`.

## Estrutura

```text
.
├── prompts/system_prompt.md   # personalidade, formato e limites da Duda
├── app/
│   ├── agent.py               # o agente e a data de hoje
│   ├── main.py                # recebe o webhook do WAHA
│   ├── ritmo.py               # buffer, "digitando" e divisão em mensagens
│   ├── memory.py              # histórico por contato, em arquivo
│   ├── midia.py               # áudio, imagem e PDF viram texto
│   ├── whatsapp.py            # envia mensagens pelo WAHA
│   └── config.py              # lê o .env
├── chat.py                    # testa no terminal
├── docker-compose.yml         # sobe o WAHA
└── .env.example               # variáveis de ambiente
```

Os passos para construir tudo isso do zero estão no curso.

---

<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/asimov-logo-para-fundo-escuro.png">
  <img src="assets/asimov-logo-para-fundo-claro.png" alt="Asimov Academy" width="120">
</picture>

</div>
