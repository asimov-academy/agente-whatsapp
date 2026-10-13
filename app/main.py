# Recebe o webhook do WAHA e entrega a mensagem pro buffer. Peça: canal.
import hashlib
import hmac
import logging

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
from app.ritmo import adicionar_mensagem

log = logging.getLogger(__name__)

app = FastAPI()

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
    if evento.get("event") != "message":
        return {"status": "ignorado"}

    mensagem = evento.get("payload") or {}
    contato = mensagem.get("from") or ""
    texto = (mensagem.get("body") or "").strip()

    if mensagem.get("fromMe"):
        return {"status": "ignorado"}
    if contato.endswith("@g.us") or contato == "status@broadcast" or not contato:
        return {"status": "ignorado"}

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
