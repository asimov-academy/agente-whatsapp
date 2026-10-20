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

**Projeto do curso 3 · Seu Agente Conhece Tudo Sobre Seu Negócio**

</div>

---

## O que ele faz

- 💬 **Ritmo de gente:** marca como lida 1 segundo depois que a mensagem chega, espera o cliente terminar de falar, mostra "digitando" (renovado enquanto pensa e digita) e responde no tempo de quem escreve.
- ✂️ **Mensagens curtas:** divide a resposta em até três mensagens, sem markdown.
- 🧠 **Memória:** lembra de cada contato, mesmo depois de reiniciar.
- 🎙️ **Áudio, foto e PDF:** entende o que o cliente mandou e responde como quem ouviu, viu e leu.
- 📅 **Sabe que dia é hoje:** entende "amanhã" e "sábado que vem".
- 📋 **Conhece o teu negócio pela planilha:** preços, horários e regras ficam numa **planilha do Google que o dono edita pelo celular**. Mudou o preço na planilha, a Duda já responde com o valor novo em até 1 minuto.
- 🎯 **Leva o cliente até o agendamento:** o objetivo dela é deixar um horário encaminhado. Ela tira as dúvidas com a planilha e convida o cliente pro próximo passo, até ele dizer o dia e o horário que prefere.
- 🙋 **Passa a vez pra um humano:** quando o cliente pede uma pessoa, a pergunta não está na planilha, ele está irritado ou o assunto não é dela, a Duda avisa o responsável **no WhatsApp** e para de responder só aquele contato. O que a equipe fala pelo celular entra no histórico dela.
- 🔁 **Volta pro atendimento:** a equipe reage com um 👍 a uma mensagem da conversa, ou a Duda volta sozinha depois de `PAUSA_MINUTOS` sem mensagem da equipe.

## Como funciona

Todo agente tem três peças. Aqui elas ficam assim:

| Peça | O que faz | Onde está |
| --- | --- | --- |
| **Canal** | leva a mensagem do WhatsApp até o código e a resposta de volta | [WAHA](https://waha.devlike.pro) + `app/whatsapp.py` e `app/main.py` |
| **Código** | buffer, ritmo, memória, mídia, a FAQ da planilha e a passagem pra um humano | `app/ritmo.py`, `app/memory.py`, `app/midia.py`, `app/faq.py` e `app/humano.py` |
| **LLM** | personalidade, objetivo, tom e exemplos de conversa | [PydanticAI](https://ai.pydantic.dev) + `prompts/system_prompt.md` |

## Como montar a FAQ

O conhecimento da Duda vem de uma planilha do Google Planilhas. O prompt guarda só a personalidade e as regras: **nenhum preço, horário ou endereço fica no código**.

1. **Faz uma cópia da planilha modelo:** [abre este link](https://docs.google.com/spreadsheets/d/13GcN7Cp9aoGImahFtweZq3imqdVEn6dBir0xxU1bTyc/copy) e confirma a cópia. Troca as perguntas e respostas pelas do teu negócio, mantendo as colunas `categoria`, `pergunta` e `resposta`.
2. **Compartilha a tua cópia:** em **Compartilhar**, em acesso geral, escolhe **"Qualquer pessoa com o link pode ver"**. Sem isso a Duda não consegue ler a planilha.
3. **Pega o link de exportação em CSV:** na barra de endereço da tua planilha, copia o código que vem depois de `/d/` e o número depois de `gid=`, e monta assim:

```text
https://docs.google.com/spreadsheets/d/CODIGO_DA_PLANILHA/export?format=csv&gid=NUMERO_DA_ABA
```

4. **Cola esse link no `.env`**, em `FAQ_PLANILHA_URL`.

A Duda lê a planilha a cada minuto. Se o Google ficar fora do ar, ela continua com a última versão e guarda uma cópia em `documentos/faq.csv`.

## Variáveis do `.env`

Além das chaves de sempre (veja o `.env.example`), o curso 3 acrescenta:

| Variável | O que é |
| --- | --- |
| `FAQ_PLANILHA_URL` | link de exportação em CSV da tua planilha de FAQ |
| `NUMERO_RESPONSAVEL` | o WhatsApp de quem recebe o aviso quando a Duda passa a vez, só dígitos, com DDI e DDD |
| `PAUSA_MINUTOS` | quanto tempo a Duda fica pausada num contato sem mensagem da equipe antes de voltar sozinha (padrão 120) |

O `BUFFER_SEGUNDOS` (quanto ela espera o cliente parar de escrever) agora tem padrão 3.

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

Pra conversar com o agente só no terminal, sem WhatsApp: `python chat.py`. Comandos do chat:

| Comando | O que faz |
| --- | --- |
| `/contato nome` | troca de contato: cada um tem o seu histórico |
| `/equipe texto` | simula a equipe respondendo pelo celular da barbearia: a mensagem entra no histórico e a Duda pausa |
| `/equipe 👍` | simula o 👍 da equipe: a Duda volta (e espera a próxima mensagem do cliente) |
| `sair` | encerra |

No chat não existe WhatsApp, então o aviso ao responsável aparece no terminal.

> ⚠️ Use um **número de teste**, nunca o teu pessoal nem o da empresa.
>
> 💻 No Mac com chip Apple, o `docker-compose.yml` já usa a imagem `devlikeapro/waha:arm`.

## Rodando na VPS

Pra deixar a Duda no ar 24 horas, numa VPS com [Docker](https://docs.docker.com/engine/install/):

1. **Domínios:** aponta dois subdomínios pro IP da VPS, por exemplo `bot.teudominio.com.br` (a Duda) e `waha.teudominio.com.br` (o painel do WAHA).
2. **`.env` preenchido** na VPS: as chaves de sempre, mais `DOMINIO`, `DOMINIO_WAHA`, `WHATSAPP_HOOK_HMAC_KEY` (uma chave longa, `openssl rand -hex 32`), `FAQ_PLANILHA_URL`, `NUMERO_RESPONSAVEL` e `PAUSA_MINUTOS`, com `WAHA_URL=http://waha:3000`.
3. **Copia o projeto** pra VPS, sem o `.env` do teu computador, o `historico/` nem o `documentos/`.
4. **Sobe tudo:**

```bash
docker compose -f docker-compose.vps.yml up -d --build
```

O Caddy gera o HTTPS sozinho. Depois é só abrir `https://waha.teudominio.com.br/dashboard`, entrar com o usuário e a senha do `.env` e ler o QR code. O webhook só aceita chamadas assinadas pelo teu WAHA. O passo a passo pra atualizar a VPS está no `CLAUDE.example.md`.

## Estrutura

```text
.
├── prompts/system_prompt.md   # personalidade, objetivo, exemplos de conversa e limites da Duda
├── app/
│   ├── agent.py               # o agente, a FAQ, a data de hoje e a ferramenta chamar_humano
│   ├── main.py                # recebe o webhook do WAHA (mensagens, equipe e o 👍)
│   ├── ritmo.py               # lido, buffer, "digitando" e divisão em mensagens
│   ├── faq.py                 # baixa a FAQ da planilha, em segundo plano
│   ├── humano.py              # pausa por contato e aviso ao responsável
│   ├── memory.py              # histórico por contato, em arquivo
│   ├── midia.py               # áudio, imagem e PDF viram texto
│   ├── whatsapp.py            # envia mensagens pelo WAHA
│   └── config.py              # lê o .env
├── chat.py                    # testa no terminal
├── Dockerfile                 # a imagem da Duda
├── Caddyfile                  # HTTPS na frente da Duda e do painel do WAHA
├── docker-compose.yml         # sobe o WAHA no teu computador
├── docker-compose.vps.yml     # sobe Caddy, Duda e WAHA na VPS
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
