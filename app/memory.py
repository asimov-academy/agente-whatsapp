# Guarda e recupera o histórico de conversa de cada contato, em arquivos JSON. Peça: código.
import asyncio
import re
from collections import defaultdict
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    RetryPromptPart,
    ToolReturnPart,
    UserPromptPart,
)

LIMITE_MENSAGENS = 30
PASTA_HISTORICO = Path(__file__).resolve().parent.parent / "historico"


_travas: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


def trava_do_contato(contato: str) -> asyncio.Lock:
    """Uma trava por contato: quem lê e grava o histórico dele segura essa trava."""
    return _travas[contato]


def _caminho(contato: str) -> Path:
    nome_seguro = re.sub(r"[^\w.@-]", "_", contato)
    return PASTA_HISTORICO / f"{nome_seguro}.json"


def _e_mensagem_do_cliente(mensagem: ModelMessage) -> bool:
    if not isinstance(mensagem, ModelRequest):
        return False
    tem_texto_do_cliente = any(isinstance(p, UserPromptPart) for p in mensagem.parts)
    tem_retorno_de_tool = any(
        isinstance(p, (ToolReturnPart, RetryPromptPart)) for p in mensagem.parts
    )
    return tem_texto_do_cliente and not tem_retorno_de_tool


def _limitar(mensagens: list[ModelMessage]) -> list[ModelMessage]:
    if len(mensagens) <= LIMITE_MENSAGENS:
        return mensagens
    recorte = mensagens[-LIMITE_MENSAGENS:]
    while recorte and not _e_mensagem_do_cliente(recorte[0]):
        recorte = recorte[1:]
    return recorte


def pegar_historico(contato: str) -> list[ModelMessage]:
    caminho = _caminho(contato)
    if not caminho.exists():
        return []
    return ModelMessagesTypeAdapter.validate_json(caminho.read_bytes())


def salvar_historico(contato: str, mensagens: list[ModelMessage]) -> None:
    PASTA_HISTORICO.mkdir(exist_ok=True)
    _caminho(contato).write_bytes(ModelMessagesTypeAdapter.dump_json(_limitar(mensagens)))


def existe_historico(contato: str) -> bool:
    return _caminho(contato).exists()


def caminho_pausa(contato: str) -> Path:
    return _caminho(contato).with_suffix(".pausa")


def adicionar_ao_historico(contato: str, novas: list[ModelMessage]) -> None:
    salvar_historico(contato, pegar_historico(contato) + novas)


def apagar_historico(contato: str) -> bool:
    """Apaga a conversa do contato (histórico e pausa). Devolve False se não havia nada."""
    existia = existe_historico(contato) or caminho_pausa(contato).exists()
    _caminho(contato).unlink(missing_ok=True)
    caminho_pausa(contato).unlink(missing_ok=True)
    return existia
