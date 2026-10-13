> **Modelo.** Copie este arquivo para `CLAUDE.md` (que fica fora do Git) e troque `IP_DA_TUA_VPS`, `bot.teudominio.com.br` e `waha.teudominio.com.br` pelos teus.

# Duda: guia para o Claude Code

Agente de atendimento da Barbearia Navalha no WhatsApp (PydanticAI + WAHA). Este arquivo diz como atualizar a Duda que roda 24 horas na VPS.

Quando o usuário pedir **"sobe a Duda pra VPS"**, siga a seção [Atualizar a Duda na VPS](#atualizar-a-duda-na-vps) sem perguntar de novo o que copiar. O trabalho acontece no notebook; a VPS é a "nuvem" onde a Duda atende de verdade.

## Regras

1. **A memória que vale é a da VPS.** A pasta `historico/` de lá guarda as conversas reais. **Nunca sobrescrever, apagar ou copiar para cima o `historico/`.** O `historico/` do notebook é só de testes locais e nunca vai para a VPS.
2. **Só copiar o `.env` se o usuário pedir.** O `.env` da VPS é diferente do notebook (chaves do WAHA, senha do painel, `WAHA_URL=http://waha:3000`, `DOMINIO`, `DOMINIO_WAHA` e `WHATSAPP_HOOK_HMAC_KEY`). Se o usuário mandar copiar, avise antes que ele vai trocar os valores da VPS.
3. **Nunca imprimir segredos** (conteúdo do `.env`, chaves, senhas) na conversa. Para conferir, mostre só se a variável existe e o tamanho do valor.
4. **Nunca usar** `docker compose down -v`, `docker volume rm` nem `rm -rf` em `historico/`. Os volumes guardam a sessão do WhatsApp (`waha_sessions`) e os certificados HTTPS (`caddy_data`).
5. O Bash e o terminal do Claude Code rodam **no Mac**. Para executar algo na VPS, é sempre via `ssh`.

## Onde a Duda roda

| O quê | Valor |
| --- | --- |
| Acesso | `ssh -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS` |
| Pasta do projeto | `/root/duda` |
| Sistema | Ubuntu 24.04, Docker e Docker Compose instalados |
| Compose da VPS | `docker-compose.vps.yml` (o `docker-compose.yml` é só do notebook) |
| Duda (webhook) | `https://bot.teudominio.com.br/webhook` |
| Painel do WAHA | `https://waha.teudominio.com.br/dashboard/` (pede login) |

Três containers, todos com `restart: unless-stopped`:

- **`caddy`**: fica na frente, nas portas 80 e 443. Gera o HTTPS sozinho e usa o `Caddyfile`. Só o `/webhook` chega na Duda (o resto responde 404), e `waha.teudominio.com.br` vai para o painel do WAHA.
- **`duda`**: o código (`app/`) e o prompt (`prompts/`), construída pelo `Dockerfile`. Sem porta publicada. Fala com o WAHA por dentro, em `http://waha:3000`.
- **`waha`**: a ponte com o WhatsApp (imagem normal, não a `arm`). A porta 3000 só em `127.0.0.1`.

O webhook só aceita chamadas assinadas pelo WAHA (header `X-Webhook-Hmac`, HMAC-SHA512 com `WHATSAPP_HOOK_HMAC_KEY`). Chamada sem assinatura volta `403`.

## Atualizar a Duda na VPS

Rode a partir da raiz do projeto, no notebook.

**1. Copiar** só o que é código. Este pacote já exclui `.env`, `historico/`, `.venv`, `.git` e o lixo do Mac:

```bash
COPYFILE_DISABLE=1 tar czf - --exclude=__pycache__ --exclude=.DS_Store \
  Dockerfile .dockerignore Caddyfile docker-compose.vps.yml requirements.txt app prompts .env.example \
  | ssh -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS 'tar xzf - -C /root/duda'
```

Não copiar: `.env`, `historico/`, `.venv/`, `__pycache__/`, `.git/`, `.claude/`, `assets/`, `README.md`, `CLAUDE.md`, `chat.py` e `docker-compose.yml` (do notebook).

Se um arquivo foi apagado ou renomeado no notebook, apague a versão antiga na VPS à mão: o `tar` só acrescenta e sobrescreve.

**2. Reconstruir** na VPS:

```bash
ssh -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS 'cd /root/duda && docker compose -f docker-compose.vps.yml up -d --build'
```

O Compose só recria o que mudou: código novo recria a `duda`; mudança no ambiente do `waha` recria o `waha` (a sessão do WhatsApp costuma voltar sozinha). Se mudou **só o `Caddyfile`**, o Caddy não recarrega sozinho, então rode também:

```bash
ssh -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS 'cd /root/duda && docker compose -f docker-compose.vps.yml restart caddy'
```

Se o `.env` da VPS precisar de variável nova (o `.env.example` mostra quais existem), avise o usuário e só mexa nele se ele pedir.

**3. Conferir** e mostrar o resultado:

```bash
ssh -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS 'cd /root/duda && docker compose -f docker-compose.vps.yml ps && docker compose -f docker-compose.vps.yml logs --tail 15 duda'
```

- Os três containers `Up`.
- A sessão do WAHA em `WORKING` (`curl -H "X-Api-Key: ..." http://127.0.0.1:3000/api/sessions` dentro da VPS, lendo a chave do `.env` sem mostrar).
- `https://bot.teudominio.com.br/webhook` sem assinatura deve responder `403`, e o painel `https://waha.teudominio.com.br/dashboard/` deve responder `401` (pede login).
- Nenhum `Traceback` nem `Falha` no log da Duda.

## Anotações úteis

- **Reconectar o WhatsApp** (se a sessão cair ou for preciso um QR novo): `ssh -t -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS 'bash /root/duda/qr.sh'`. O script desenha o QR no terminal e avisa quando conectar. Ele existe só na VPS.
- **Painel por túnel SSH**, sem passar pela internet: `ssh -i ~/.ssh/hostinger_curso -L 3001:127.0.0.1:3000 root@IP_DA_TUA_VPS` e abrir `http://localhost:3001/dashboard`.
- Dentro de script rodado por `ssh ... 'bash -s' < arquivo`, use `docker compose exec -T ... < /dev/null`, senão o comando engole o resto do script.
- O Ubuntu da VPS pode ter reinício pendente (kernel). Se for reiniciar, os containers voltam sozinhos; depois confira que a sessão voltou a `WORKING`.
- O prompt (`prompts/system_prompt.md`) e o código só valem na VPS depois do passo 1 e do passo 2.
