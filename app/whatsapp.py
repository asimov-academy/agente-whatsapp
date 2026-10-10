# Envia mensagens e sinais de presença (lido, digitando) pelo WhatsApp via API do WAHA. Peça: canal.
import httpx

from app.config import WAHA_API_KEY, WAHA_URL


async def _post(caminho: str, corpo: dict) -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        resposta = await client.post(
            f"{WAHA_URL}{caminho}",
            headers={"X-Api-Key": WAHA_API_KEY},
            json=corpo,
        )
        resposta.raise_for_status()


async def enviar_mensagem(chat_id: str, texto: str, sessao: str = "default") -> None:
    await _post("/api/sendText", {"session": sessao, "chatId": chat_id, "text": texto})


async def marcar_como_lida(chat_id: str, sessao: str = "default") -> None:
    await _post("/api/sendSeen", {"session": sessao, "chatId": chat_id})


async def comecar_digitando(chat_id: str, sessao: str = "default") -> None:
    await _post("/api/startTyping", {"session": sessao, "chatId": chat_id})


async def parar_digitando(chat_id: str, sessao: str = "default") -> None:
    await _post("/api/stopTyping", {"session": sessao, "chatId": chat_id})
