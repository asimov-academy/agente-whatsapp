# Envia mensagens e sinais de presença (lido, digitando) pelo WhatsApp via API do WAHA. Peça: canal.
from collections import deque

import httpx

from app.config import WAHA_API_KEY, WAHA_URL


# Ids das mensagens que a própria Duda mandou. O WAHA devolve cada uma como evento com fromMe,
# e isso precisa ser distinguido de uma resposta que a equipe digitou no celular.
_ids_enviados: deque[str] = deque(maxlen=1000)


def _guardar_ids(dados) -> None:
    id_ = dados.get("id") if isinstance(dados, dict) else None
    if isinstance(id_, dict):
        candidatos = [id_.get("_serialized"), id_.get("id")]
    else:
        candidatos = [id_]
    for c in candidatos:
        if isinstance(c, str) and c:
            _ids_enviados.append(c)
            _ids_enviados.append(c.rsplit("_", 1)[-1])


def foi_enviada_pela_duda(id_da_mensagem: str) -> bool:
    return bool(id_da_mensagem) and (
        id_da_mensagem in _ids_enviados or id_da_mensagem.rsplit("_", 1)[-1] in _ids_enviados
    )


async def _post(caminho: str, corpo: dict) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        resposta = await client.post(
            f"{WAHA_URL}{caminho}",
            headers={"X-Api-Key": WAHA_API_KEY},
            json=corpo,
        )
        resposta.raise_for_status()
        try:
            return resposta.json()
        except ValueError:
            return {}


async def enviar_mensagem(chat_id: str, texto: str, sessao: str = "default") -> None:
    dados = await _post("/api/sendText", {"session": sessao, "chatId": chat_id, "text": texto})
    _guardar_ids(dados)


async def marcar_como_lida(chat_id: str, sessao: str = "default") -> None:
    await _post("/api/sendSeen", {"session": sessao, "chatId": chat_id})


async def comecar_digitando(chat_id: str, sessao: str = "default") -> None:
    await _post("/api/startTyping", {"session": sessao, "chatId": chat_id})


async def parar_digitando(chat_id: str, sessao: str = "default") -> None:
    await _post("/api/stopTyping", {"session": sessao, "chatId": chat_id})


async def resolver_chat_id(numero: str, sessao: str = "default") -> str | None:
    """Descobre o id de chat de um número de telefone (pode ser @lid). None se o número não tem WhatsApp.

    Mandar direto pra "numero@c.us" falha com "No LID for user" quando o WhatsApp ainda não
    ligou esse número ao id novo (LID) dele. Perguntar antes resolve a ligação.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resposta = await client.get(
            f"{WAHA_URL}/api/contacts/check-exists",
            headers={"X-Api-Key": WAHA_API_KEY},
            params={"phone": numero, "session": sessao},
        )
        resposta.raise_for_status()
        dados = resposta.json()
    return dados.get("chatId") if dados.get("numberExists") else None
