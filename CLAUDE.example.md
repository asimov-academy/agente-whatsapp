> **Modelo.** Copie este arquivo para `CLAUDE.md` (que fica fora do Git) e troque `IP_DA_TUA_VPS`, `bot.teudominio.com.br` e `waha.teudominio.com.br` pelos teus.

# Duda: guia para o Claude Code

Agente de atendimento da Barbearia Navalha no WhatsApp (PydanticAI + WAHA). Este arquivo diz como atualizar a Duda que roda 24 horas na VPS.

Quando o usuário pedir **"sobe a Duda pra VPS"**, siga a seção [Atualizar a Duda na VPS](#atualizar-a-duda-na-vps) sem perguntar de novo o que copiar. O trabalho acontece no notebook; a VPS é a "nuvem" onde a Duda atende de verdade.

## Regras

1. **A memória que vale é a da VPS.** A pasta `historico/` de lá guarda as conversas reais. **Nunca sobrescrever, apagar ou copiar para cima o `historico/`.** O `historico/` do notebook é só de testes locais e nunca vai para a VPS. O mesmo vale para a pasta **`documentos/`** da VPS (a cópia da FAQ): **nunca é sobrescrita**, e a `documentos/` do notebook nunca vai para lá.
2. **Só copiar o `.env` se o usuário pedir.** O `.env` da VPS é diferente do notebook (chaves do WAHA, senha do painel, `WAHA_URL=http://waha:3000`, `DOMINIO`, `DOMINIO_WAHA`, `WHATSAPP_HOOK_HMAC_KEY`, `FAQ_PLANILHA_URL`, `NUMERO_RESPONSAVEL` e `PAUSA_MINUTOS`). Se o usuário mandar copiar, avise antes que ele vai trocar os valores da VPS.
3. **Nunca imprimir segredos** (conteúdo do `.env`, chaves, senhas) na conversa. Para conferir, mostre só se a variável existe e o tamanho do valor.
4. **Nunca usar** `docker compose down -v`, `docker volume rm` nem `rm -rf` em `historico/` ou `documentos/`. Os volumes guardam a sessão do WhatsApp (`waha_sessions`) e os certificados HTTPS (`caddy_data`).
5. O Bash e o terminal do Claude Code rodam **no Mac**. Para executar algo na VPS, é sempre via `ssh`.

## De onde vem o conhecimento da Duda

Preço, horário, endereço e regras da barbearia **vêm da planilha de FAQ do Google Planilhas**, no link em `FAQ_PLANILHA_URL` (o link de exportação em CSV, no `.env`). O `app/faq.py` baixa a planilha, guarda na memória por 60 segundos e salva uma cópia em `documentos/faq.csv`. Se o download falhar, a Duda usa a última versão boa ou essa cópia.

- **Pra mudar preço ou qualquer informação, é só editar a planilha.** Não precisa copiar nada nem reconstruir a VPS: em até 60 segundos a Duda já responde com o valor novo.
- A planilha precisa ter as colunas `categoria`, `pergunta` e `resposta`, e estar aberta a quem tem o link.
- O `prompts/system_prompt.md` guarda a personalidade, o **objetivo da Duda (levar o cliente a deixar um horário encaminhado)**, o jeito de conduzir a conversa, o formato, os limites e uma seção de **exemplos de conversa inteira** (`## Exemplos de conversa`, dentro de Formato). Os exemplos **nunca levam preço, horário nem endereço**: esses dados ficam entre colchetes (como `[preço do corte]`) e vêm só da planilha. O prompt não tem nenhum dado da barbearia.
- A pasta `documentos/` da VPS é um volume e **nunca é sobrescrita** por cópia do notebook.

## Passar a vez pra um humano

A Duda tem a tool **`chamar_humano`** (`motivo` e `resumo`). Ela usa quando o cliente pede uma pessoa, quando a pergunta não está na FAQ, quando o cliente está irritado ou reclamando, ou quando o assunto não é pra ela resolver (como problema com pagamento). Quando roda, a tool faz duas coisas:

- **Pausa o contato.** A pausa é um arquivo `<contato>.pausa` **dentro do `historico/` da VPS**, que nunca é sobrescrito, então ela continua valendo se a Duda reiniciar. Pausado, a Duda não responde nada pra esse contato (nem lido, nem digitando), mas a conversa segue sendo salva no histórico: o que o cliente manda entra como mensagem do cliente, e o que a equipe responde pelo WhatsApp da barbearia entra marcado como `[atendente humano]`.
- **Avisa o responsável** pelo WhatsApp, pelo WAHA, no número de `NUMERO_RESPONSAVEL` (só dígitos, com DDI e DDD), com o número do cliente, o motivo e o resumo.

Pra receber o que a equipe responde pelo celular, o WAHA manda o evento `message.any` no lugar de `message` (`WHATSAPP_HOOK_EVENTS`, nos dois compose): só ele, porque com os dois a mensagem do cliente chegaria duas vezes. O 👍 da equipe chega pelo evento `message.reaction`. Se `NUMERO_RESPONSAVEL` estiver vazio, a tool não pausa e a Duda avisa o cliente que deu um problema.

- **Como a Duda volta a responder um contato:** (1) a equipe reage com um **👍** a qualquer mensagem da conversa, pelo celular da barbearia: a Duda tira a pausa e não manda nada, espera o cliente falar (o 👍 fica na mensagem, como um gesto normal); (2) por tempo: quando o cliente escreve e já passou `PAUSA_MINUTOS` (120) desde a última mensagem da equipe (ou desde a pausa), ela tira a pausa e responde normal; (3) na mão: apagar o arquivo `<contato>.pausa` em `historico/` na VPS.
- **Quando a equipe fala sozinha:** o que a equipe escreve pelo celular numa conversa que a Duda já teve entra no histórico marcado `[atendente humano]:` e **pausa o contato** (o dono assumiu), guardando a hora da última mensagem da equipe. A Duda reconhece a própria mensagem pelo campo `source` do evento (`api` é ela, `app` é a equipe). Grupos, status e listas de transmissão são ignorados.
- Apagar só o `<contato>.json` limpa a conversa, mas não a pausa: se for zerar um contato, apague também o `.pausa`.
- **`#reset`:** quando o cliente (ou você, no celular de teste) manda só `#reset` para a Duda, ela apaga o histórico e a pausa **daquela conversa**, descarta o que estava esperando no buffer e responde `Agente Reiniciado!`. O comando não vai pro agente nem entra no histórico. Vale pra qualquer contato, só pra própria conversa. No `chat.py` também funciona.
- No `chat.py` (notebook) o aviso aparece no terminal, `/retomar` volta a Duda e `/equipe texto` simula a equipe pelo celular (`/equipe 👍` simula o 👍 e devolve a conversa).

## O ritmo da Duda

Tudo isso mora em `app/ritmo.py` (e o download da FAQ em `app/faq.py`). Os tempos são constantes no topo do arquivo; o buffer vem do `.env`.

- **Lido:** a conversa é marcada como lida **1 segundo** depois que a mensagem do cliente chega, sem esperar o buffer (e, no áudio, sem esperar a transcrição). Contato pausado com um humano não é marcado.
- **Espera:** a Duda só responde depois de `BUFFER_SEGUNDOS` sem mensagem nova do cliente (padrão do código: 6; na VPS o `.env` define o valor em uso). A contagem recomeça a cada mensagem nova.
- **Digitando:** cada mensagem tem 1 s + 0,03 s por caractere de "digitando", **no mínimo 1,5 s e no máximo 4 s**. Na primeira mensagem, o tempo que o agente levou pensando já conta. O sinal é **renovado a cada 5 segundos** (o WhatsApp apaga o "digitando" sozinho), religa 0,5 s depois de cada envio (enviar apaga o "digitando") e é desligado mesmo se der erro. A Duda **não marca a sessão como online**: isso faz o celular da barbearia parar de receber notificação.
- **FAQ em segundo plano:** com a FAQ já na memória, a Duda responde na hora com ela e, quando o cache de 60 s vence, baixa a nova em segundo plano (a nova entra quando terminar). Só na primeira vez, sem FAQ na memória, ela espera o download ou usa a cópia em `documentos/`.
- **Medição:** cada resposta deixa no log da Duda uma linha `Tempos de ...: espera= fila= sinais= agente= resumo_da_midia= digitando=[...] envio= total=`. Pra ler: `docker compose -f docker-compose.vps.yml logs duda | grep Tempos`.

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
- **`duda`**: o código (`app/`) e o prompt (`prompts/`), construída pelo `Dockerfile`. Sem porta publicada. Fala com o WAHA por dentro, em `http://waha:3000`. Monta `historico/` e `documentos/` da VPS como volumes.
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

Não copiar: `.env`, `historico/`, `documentos/`, `.venv/`, `__pycache__/`, `.git/`, `.claude/`, `assets/`, `README.md`, `CLAUDE.md`, `chat.py` e `docker-compose.yml` (do notebook).

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
- O WAHA manda **só** os eventos `message.any` e `message.reaction` no webhook (`docker compose -f docker-compose.vps.yml exec -T waha sh -c 'echo $WHATSAPP_HOOK_EVENTS'` deve mostrar `message.any,message.reaction`, sem `message` sozinho).
- A FAQ carrega na VPS: `docker compose -f docker-compose.vps.yml exec -T duda python -c "from app.faq import texto_da_faq; print(len(texto_da_faq()))"` deve mostrar um número maior que zero, e `documentos/faq.csv` deve existir lá.

## Anotações úteis

- **Reconectar o WhatsApp** (se a sessão cair ou for preciso um QR novo): `ssh -t -i ~/.ssh/hostinger_curso root@IP_DA_TUA_VPS 'bash /root/duda/qr.sh'`. O script desenha o QR no terminal e avisa quando conectar. Ele existe só na VPS.
- **Painel por túnel SSH**, sem passar pela internet: `ssh -i ~/.ssh/hostinger_curso -L 3001:127.0.0.1:3000 root@IP_DA_TUA_VPS` e abrir `http://localhost:3001/dashboard`.
- Dentro de script rodado por `ssh ... 'bash -s' < arquivo`, use `docker compose exec -T ... < /dev/null`, senão o comando engole o resto do script.
- O Ubuntu da VPS pode ter reinício pendente (kernel). Se for reiniciar, os containers voltam sozinhos; depois confira que a sessão voltou a `WORKING`.
- O prompt (`prompts/system_prompt.md`) e o código só valem na VPS depois do passo 1 e do passo 2.
