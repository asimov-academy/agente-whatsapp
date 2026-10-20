# Recebe o webhook do WAHA e entrega a mensagem pro buffer. Peça: canal.
import asyncio
import hashlib
import hmac
import logging
from collections import deque

from fastapi import FastAPI, HTTPException, Request

from app import config  # noqa: F401  (carrega o .env antes do agente)
from app.config import WHATSAPP_HOOK_HMAC_KEY
from app.midia import (
    baixar_midia,
    descrever_imagem,
    ler_documento,
    nome_do_arquivo_de_audio,
    transcrever_audio,
)
from app.humano import e_joinha, tratar_joinha_da_equipe, tratar_mensagem_da_equipe
from app.ritmo import (
    adicionar_mensagem,
    agendar_leitura,
    e_comando_reiniciar,
    reiniciar_em_segundo_plano,
)
from app.whatsapp import foi_enviada_pela_duda

logging.basicConfig(format="%(levelname)s:     %(name)s: %(message)s")
logging.getLogger("app").setLevel(logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI()

# O WAHA pode mandar o mesmo evento mais de uma vez (message e message.any): conta só uma.
_ids_vistos: deque[str] = deque(maxlen=1000)
_tarefas: set[asyncio.Task] = set()

if not WHATSAPP_HOOK_HMAC_KEY:
    log.warning("WHATSAPP_HOOK_HMAC_KEY vazia: o webhook aceita qualquer chamada. Só use assim em testes locais.")


def _assinatura_valida(corpo: bytes, assinatura_recebida: str | None) -> bool:
    # O WAHA manda no header X-Webhook-Hmac o HMAC-SHA512 (hex) do corpo cru, com a nossa chave.
    if not WHATSAPP_HOOK_HMAC_KEY:
        return True
    if not assinatura_recebida:
        return False
    esperada = hmac.new(WHATSAPP_HOOK_HMAC_KEY.encode(), corpo, hashlib.sha512).hexdigest()
    return hmac.compare_digest(esperada, assinatura_recebida.strip().lower())


@app.post("/webhook")
async def webhook(request: Request):
    corpo = await request.body()
    if not _assinatura_valida(corpo, request.headers.get("x-webhook-hmac")):
        raise HTTPException(status_code=403, detail="Assinatura inválida")

    evento = await request.json()
    if evento.get("event") not in ("message", "message.any", "message.reaction"):
        return {"status": "ignorado"}

    mensagem = evento.get("payload") or {}
    id_da_mensagem = mensagem.get("id") or ""
    if id_da_mensagem:
        if id_da_mensagem in _ids_vistos:
            return {"status": "ignorado"}
        _ids_vistos.append(id_da_mensagem)

    if evento.get("event") == "message.reaction":
        return _reacao_da_equipe(mensagem)

    if mensagem.get("fromMe"):
        return _mensagem_do_numero_da_barbearia(mensagem)

    contato = mensagem.get("from") or ""
    texto = (mensagem.get("body") or "").strip()
    if _e_grupo_status_ou_broadcast(contato) or not contato:
        return {"status": "ignorado"}

    if not mensagem.get("hasMedia") and e_comando_reiniciar(texto):
        reiniciar_em_segundo_plano(contato, evento.get("session") or "default")
        return {"status": "ok"}

    if mensagem.get("hasMedia") or texto:
        # "Lido" 1 s depois que chega, sem esperar a transcrição de áudio nem o buffer.
        agendar_leitura(contato, evento.get("session") or "default")

    if mensagem.get("hasMedia"):
        midia = mensagem.get("media") or {}
        mimetype = midia.get("mimetype") or ""
        if mimetype.startswith("audio/"):
            texto = await _texto_do_audio(contato, midia, mimetype)
        elif mimetype.startswith("image/"):
            texto = await _texto_da_imagem(contato, midia, mimetype, legenda=texto)
        elif mimetype.split(";")[0].strip() == "application/pdf":
            texto = await _texto_do_pdf(contato, midia, legenda=texto)
        else:
            legenda = texto
            texto = f"[o cliente mandou um arquivo do tipo {mimetype or 'desconhecido'}]"
            if legenda:
                texto += f"\nLegenda: {legenda}"
    elif not texto:
        return {"status": "ignorado"}

    adicionar_mensagem(contato, texto, evento.get("session") or "default")
    return {"status": "ok"}


async def _texto_do_audio(contato: str, midia: dict, mimetype: str) -> str:
    try:
        if not midia.get("url"):
            raise ValueError(f"WAHA não baixou o áudio: {midia.get('error')}")
        conteudo = await baixar_midia(midia["url"])
        nome = nome_do_arquivo_de_audio(mimetype, midia.get("filename"))
        transcricao = await transcrever_audio(conteudo, nome)
    except Exception:
        log.exception("Falha ao transcrever o áudio de %s", contato)
        return "[áudio do cliente]: (não foi possível entender o áudio)"
    return f"[áudio do cliente]: {transcricao}"


async def _texto_da_imagem(contato: str, midia: dict, mimetype: str, legenda: str) -> str:
    try:
        if not midia.get("url"):
            raise ValueError(f"WAHA não baixou a imagem: {midia.get('error')}")
        descricao = await descrever_imagem(midia["url"], mimetype)
    except Exception:
        log.exception("Falha ao descrever a imagem de %s", contato)
        descricao = "(não foi possível ver a imagem)"
    texto = f"[imagem enviada pelo cliente]: {descricao}"
    if legenda:
        texto += f"\nLegenda: {legenda}"
    return texto


async def _texto_do_pdf(contato: str, midia: dict, legenda: str) -> str:
    nome = midia.get("filename") or "documento.pdf"
    try:
        if not midia.get("url"):
            raise ValueError(f"WAHA não baixou o documento: {midia.get('error')}")
        conteudo = await baixar_midia(midia["url"])
        conteudo_do_pdf = await ler_documento(conteudo, nome)
    except Exception:
        log.exception("Falha ao ler o documento de %s", contato)
        conteudo_do_pdf = "(não foi possível ler o documento)"
    texto = f"[documento PDF enviado pelo cliente, arquivo {nome}]: {conteudo_do_pdf}"
    if legenda:
        texto += f"\nLegenda: {legenda}"
    return texto


def _e_grupo_status_ou_broadcast(contato: str) -> bool:
    return contato.endswith(("@g.us", "@broadcast"))


def _em_segundo_plano(corrotina) -> None:
    # O WAHA não espera, e o histórico pode estar em uso pela Duda.
    tarefa = asyncio.create_task(corrotina)
    _tarefas.add(tarefa)
    tarefa.add_done_callback(_tarefas.discard)


def _mensagem_do_numero_da_barbearia(mensagem: dict) -> dict:
    """Mensagem com fromMe. source "api" é a própria Duda (já está no histórico);
    "app" é alguém da equipe pelo celular."""
    id_da_mensagem = mensagem.get("id") or ""
    origem = mensagem.get("source")
    contato = _contato_da_mensagem_enviada(mensagem)
    log.info("fromMe: origem=%s, enviada pela Duda=%s", origem, foi_enviada_pela_duda(id_da_mensagem))

    if origem == "api" or foi_enviada_pela_duda(id_da_mensagem):
        return {"status": "ignorado"}
    if not contato or _e_grupo_status_ou_broadcast(contato):
        return {"status": "ignorado"}

    texto = (mensagem.get("body") or "").strip()
    if not texto and mensagem.get("hasMedia"):
        texto = "(mandou um áudio, imagem ou arquivo)"
    if not texto:
        return {"status": "ignorado"}

    _em_segundo_plano(tratar_mensagem_da_equipe(contato, texto))
    return {"status": "ok"}


def _reacao_da_equipe(mensagem: dict) -> dict:
    """Um 👍 da equipe (fromMe) em qualquer mensagem da conversa devolve o atendimento pra Duda."""
    reacao = mensagem.get("reaction") or {}
    if not mensagem.get("fromMe") or not e_joinha(reacao.get("text") or ""):
        return {"status": "ignorado"}
    partes = (reacao.get("messageId") or "").split("_")  # fromMe_chatId_idDaMensagem
    contato = partes[1] if len(partes) >= 3 else ""
    if not contato or _e_grupo_status_ou_broadcast(contato):
        return {"status": "ignorado"}
    _em_segundo_plano(tratar_joinha_da_equipe(contato))
    return {"status": "ok"}


def _contato_da_mensagem_enviada(mensagem: dict) -> str:
    """Numa mensagem enviada por nós, o cliente é o destinatário (to), não o remetente (from)."""
    remetente = mensagem.get("from") or ""
    id_da_mensagem = mensagem.get("id") or ""
    partes = id_da_mensagem.split("_")  # fromMe_chatId_idDaMensagem
    do_id = partes[1] if len(partes) >= 3 else ""
    for candidato in (mensagem.get("to") or "", do_id):
        if candidato and candidato != remetente:
            return candidato
    return ""
