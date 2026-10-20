# Passa a vez pra um humano: pausa a Duda por contato e avisa o responsável. Peça: código.
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app import config
from app.memory import (
    adicionar_ao_historico,
    caminho_pausa,
    existe_historico,
    trava_do_contato,
)
from app.whatsapp import enviar_mensagem, resolver_chat_id

log = logging.getLogger(__name__)

MARCA_ATENDENTE = "[atendente humano]:"


@dataclass
class Contexto:
    """O que a ferramenta chamar_humano precisa saber sobre a conversa que está rodando."""

    contato: str
    sessao: str = "default"
    terminal: bool = False  # chat.py: o aviso aparece no terminal em vez de ir pro WhatsApp


# ---- pausa por contato (um arquivo na pasta historico/, que sobrevive a reinício) ----

def _agora() -> datetime:
    return datetime.now(ZoneInfo("America/Sao_Paulo"))


def _ler_pausa(contato: str) -> dict:
    try:
        return json.loads(caminho_pausa(contato).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _gravar_pausa(contato: str, dados: dict) -> None:
    caminho = caminho_pausa(contato)
    caminho.parent.mkdir(exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def esta_pausado(contato: str) -> bool:
    return caminho_pausa(contato).exists()


def pausar(contato: str, motivo: str, resumo: str) -> None:
    _gravar_pausa(
        contato,
        {
            "desde": _agora().isoformat(timespec="seconds"),
            "motivo": motivo,
            "resumo": resumo,
            "ultima_mensagem_equipe": None,
        },
    )


def retomar(contato: str) -> bool:
    """Tira a pausa. Devolve False se o contato não estava pausado."""
    caminho = caminho_pausa(contato)
    existia = caminho.exists()
    caminho.unlink(missing_ok=True)
    return existia


def pausa_ativa(contato: str) -> bool:
    """O contato está pausado? Se a pausa já passou de PAUSA_MINUTOS, tira ela e devolve False.

    O prazo conta desde a última mensagem da equipe, ou desde a pausa se a equipe não falou nada.
    """
    caminho = caminho_pausa(contato)
    if not caminho.exists():
        return False
    dados = _ler_pausa(contato)
    referencia = dados.get("ultima_mensagem_equipe") or dados.get("desde")
    try:
        desde = datetime.fromisoformat(referencia)
    except (TypeError, ValueError):
        desde = datetime.fromtimestamp(caminho.stat().st_mtime, ZoneInfo("America/Sao_Paulo"))
    if (_agora() - desde).total_seconds() >= config.PAUSA_MINUTOS * 60:
        retomar(contato)
        log.info("Pausa de %s passou de %s min: a Duda volta a responder.", contato, config.PAUSA_MINUTOS)
        return False
    return True


def _marcar_mensagem_da_equipe(contato: str) -> None:
    """A equipe falou: guarda a hora e, se o contato não estava pausado, pausa (o dono assumiu)."""
    dados = _ler_pausa(contato) if esta_pausado(contato) else {
        "desde": _agora().isoformat(timespec="seconds"),
        "motivo": "A equipe assumiu a conversa pelo celular",
        "resumo": "",
    }
    dados["ultima_mensagem_equipe"] = _agora().isoformat(timespec="seconds")
    _gravar_pausa(contato, dados)


def e_joinha(reacao: str) -> bool:
    """A reação é um 👍 (com ou sem cor de pele)?"""
    return re.sub("[\U0001F3FB-\U0001F3FF\uFE0F]", "", reacao).strip() == "\U0001F44D"


# ---- aviso ao responsável ----


_ERRO_AO_AVISAR = (
    "ERRO: não consegui avisar a equipe agora e a conversa NÃO foi pausada. "
    "Não promete que alguém vai responder: diz que deu um probleminha e que o "
    "cliente pode mandar a mensagem de novo daqui a pouco."
)


def _so_digitos(numero: str) -> str:
    return "".join(c for c in numero if c.isdigit())


def _descrever_cliente(contato: str) -> str:
    if contato.endswith("@c.us"):
        return "+" + contato.removesuffix("@c.us")
    return f"{contato} (o WhatsApp não mostrou o número desse contato)"


def texto_do_aviso(contato: str, motivo: str, resumo: str) -> str:
    return (
        "🔔 A Duda passou a vez pra equipe\n\n"
        f"Cliente: {_descrever_cliente(contato)}\n"
        f"Motivo: {motivo}\n"
        f"Resumo: {resumo}\n\n"
        "A Duda está pausada pra esse cliente. É só responder por aqui."
    )


async def chamar_humano_agora(contexto: Contexto, motivo: str, resumo: str) -> str:
    """Avisa o responsável e pausa a Duda pra esse contato. O texto devolvido é lido pela Duda."""
    aviso = texto_do_aviso(contexto.contato, motivo, resumo)

    if contexto.terminal:
        print(f"\n[AVISO AO RESPONSÁVEL: no WhatsApp isto iria pro NUMERO_RESPONSAVEL]\n{aviso}\n")
    else:
        numero = config.NUMERO_RESPONSAVEL.strip()
        if not numero:
            log.error("NUMERO_RESPONSAVEL não está definido: ninguém foi avisado.")
            return _ERRO_AO_AVISAR
        try:
            destino = numero if "@" in numero else await resolver_chat_id(_so_digitos(numero), contexto.sessao)
            if not destino:
                log.error("NUMERO_RESPONSAVEL (%s) não tem WhatsApp: ninguém foi avisado.", numero)
                return _ERRO_AO_AVISAR
            await enviar_mensagem(destino, aviso, contexto.sessao)
        except Exception:
            log.exception("Falha ao avisar o responsável sobre %s", contexto.contato)
            return _ERRO_AO_AVISAR

    pausar(contexto.contato, motivo, resumo)
    return (
        "Pronto: a equipe foi avisada e a conversa com este cliente está pausada. "
        "Escreve ao cliente uma mensagem curta dizendo que alguém da equipe vai responder por aqui."
    )


# ---- o que acontece no histórico enquanto a Duda está pausada ----


def anexar_mensagem_do_cliente(contato: str, texto: str) -> None:
    adicionar_ao_historico(contato, [ModelRequest(parts=[UserPromptPart(content=texto)])])


def anexar_mensagem_do_atendente(contato: str, texto: str) -> bool:
    """Grava a resposta da equipe no histórico, marcada como atendente humano, e marca a pausa.

    Só vale pra conversa que a Duda já teve (ou contato pausado): o número da barbearia também
    conversa com gente que nunca falou com ela, e isso não vira histórico.
    """
    if not (esta_pausado(contato) or existe_historico(contato)):
        return False
    resposta = ModelResponse(parts=[TextPart(content=f"{MARCA_ATENDENTE} {texto}")])
    adicionar_ao_historico(contato, [resposta])
    _marcar_mensagem_da_equipe(contato)
    return True


def processar_mensagem_da_equipe(contato: str, texto: str) -> str:
    """Mensagem que a equipe mandou pelo celular: entra no histórico e pausa o contato.

    Devolve "registrada" ou "ignorada" (conversa que a Duda nunca teve).
    Quem chama já segura a trava do contato (o chat.py, sem asyncio, nem precisa).
    """
    return "registrada" if anexar_mensagem_do_atendente(contato, texto) else "ignorada"


def processar_joinha_da_equipe(contato: str) -> str:
    """A equipe reagiu com 👍 a uma mensagem da conversa: a Duda volta (mas não manda nada)."""
    return "voltou" if retomar(contato) else "nada"


async def tratar_mensagem_da_equipe(contato: str, texto: str) -> str:
    async with trava_do_contato(contato):
        return processar_mensagem_da_equipe(contato, texto)


async def tratar_joinha_da_equipe(contato: str) -> str:
    async with trava_do_contato(contato):
        return processar_joinha_da_equipe(contato)
