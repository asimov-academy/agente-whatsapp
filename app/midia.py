# Transforma mídia do WhatsApp (por enquanto só áudio) em texto antes de chegar no agente. Peça: código.
import base64
import logging
import os
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI

from app.config import WAHA_API_KEY, WAHA_URL

log = logging.getLogger(__name__)

EXTENSOES_DE_AUDIO = {
    "audio/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/aac": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/webm": "webm",
}


async def baixar_midia(url: str) -> bytes:
    # A URL vem do evento do WAHA. A API key só vai pro próprio WAHA: o endereço do host
    # é sempre o WAHA_URL, só o caminho do arquivo é aproveitado da URL do evento.
    partes = urlsplit(url)
    destino = f"{WAHA_URL}{partes.path}" + (f"?{partes.query}" if partes.query else "")
    async with httpx.AsyncClient(timeout=60) as client:
        resposta = await client.get(destino, headers={"X-Api-Key": WAHA_API_KEY})
        resposta.raise_for_status()
        return resposta.content


def nome_do_arquivo_de_audio(mimetype: str, nome_original: str | None = None) -> str:
    # O Whisper decide o formato pela extensão do nome, então ela precisa estar certa.
    # O áudio do WhatsApp chega como "audio/ogg; codecs=opus" -> .ogg
    tipo = mimetype.split(";")[0].strip().lower()
    extensao = EXTENSOES_DE_AUDIO.get(tipo)
    if extensao is None and nome_original and "." in nome_original:
        extensao = nome_original.rsplit(".", 1)[1].lower()
    return f"audio.{extensao or 'ogg'}"


async def transcrever_audio(conteudo: bytes, nome_arquivo: str) -> str:
    # Mesma chave do OpenRouter: ele expõe o Whisper da OpenAI na API de transcrição.
    cliente = AsyncOpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    transcricao = await cliente.audio.transcriptions.create(
        model="openai/whisper-1",
        file=(nome_arquivo, conteudo),
        language="pt",
    )
    return transcricao.text.strip()


PROMPT_IMAGEM = (
    "Descreva esta imagem em português, de forma objetiva. "
    "Inclua qualquer texto que apareça nela, transcrito exatamente como está escrito."
)


LIMITE_DOCUMENTO_BYTES = 20 * 1024 * 1024
LIMITE_DOCUMENTO_CARACTERES = 4000

PROMPT_DOCUMENTO = (
    "Transcreva o conteúdo principal deste documento em texto, no idioma em que ele está "
    f"escrito, em até {LIMITE_DOCUMENTO_CARACTERES} caracteres. Mantenha nomes, valores, "
    "datas e números exatamente como estão. Não comente nem resuma além do necessário."
)


async def _perguntar_ao_modelo_de_midia(instrucao: str, anexo: dict | None = None) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        resposta = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
            json={
                "model": os.environ["MODELO_MIDIA"],
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": instrucao}, *([anexo] if anexo else [])],
                    }
                ],
            },
        )
        resposta.raise_for_status()
        return resposta.json()["choices"][0]["message"]["content"].strip()


async def descrever_imagem(url: str, mimetype: str = "image/jpeg") -> str:
    # O link do WAHA é local (localhost) e exige a API key, então o modelo não conseguiria abri-lo.
    # Por isso a imagem é baixada aqui e enviada ao modelo embutida na própria requisição.
    conteudo = await baixar_midia(url)
    tipo = mimetype.split(";")[0].strip() or "image/jpeg"
    imagem_embutida = f"data:{tipo};base64,{base64.b64encode(conteudo).decode()}"
    anexo = {"type": "image_url", "image_url": {"url": imagem_embutida}}
    return await _perguntar_ao_modelo_de_midia(PROMPT_IMAGEM, anexo)


async def ler_documento(conteudo: bytes, nome_arquivo: str) -> str:
    if len(conteudo) > LIMITE_DOCUMENTO_BYTES:
        raise ValueError(f"Documento grande demais: {len(conteudo)} bytes")
    arquivo_embutido = f"data:application/pdf;base64,{base64.b64encode(conteudo).decode()}"
    anexo = {"type": "file", "file": {"filename": nome_arquivo, "file_data": arquivo_embutido}}
    texto = await _perguntar_ao_modelo_de_midia(PROMPT_DOCUMENTO, anexo)
    return texto[:LIMITE_DOCUMENTO_CARACTERES]


PREFIXOS_DE_MIDIA_LONGA = ("[imagem enviada pelo cliente]", "[documento PDF enviado pelo cliente")

PROMPT_RESUMO = (
    "Resuma em uma frase curta, em português, com no máximo 200 caracteres, o que o cliente "
    "enviou. Não inclua dados pessoais (CPF, CNPJ, endereços, telefones, números de conta, "
    "de documento ou de identificação). Se houver uma legenda escrita pelo cliente, mantenha "
    "ela. Responda só com o resumo."
)


def e_midia_longa(texto: str) -> bool:
    return texto.startswith(PREFIXOS_DE_MIDIA_LONGA)


async def resumir_para_historico(texto: str) -> str:
    # No histórico fica só um resumo curto da imagem ou do documento: o conteúdo completo
    # só é necessário na resposta de agora e pesaria (e guardaria dados pessoais) nas próximas.
    prefixo = texto.split("]: ", 1)[0]
    try:
        resumo = await _perguntar_ao_modelo_de_midia(f"{PROMPT_RESUMO}\n\n{texto}")
        resumo = " ".join(resumo.split())[:300]
    except Exception:
        log.exception("Falha ao resumir a mídia para o histórico")
        resumo = "(conteúdo não guardado)"
    return f"{prefixo}, resumo]: {resumo}"
