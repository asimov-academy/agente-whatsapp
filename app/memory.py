# Guarda e recupera o histórico de conversa de cada contato, em arquivos JSON. Peça: código.
import re
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
