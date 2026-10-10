# Junta as mensagens picadas de cada contato e responde só quando ele para de falar. Peça: código.
import asyncio
import logging
import re
import time
from collections import defaultdict

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from app.config import BUFFER_SEGUNDOS  # isort: skip  (carrega o .env antes do agente)
from app.agent import agent
from app.memory import pegar_historico, salvar_historico
from app.midia import e_midia_longa, resumir_para_historico
from app.whatsapp import (
    comecar_digitando,
    enviar_mensagem,
    marcar_como_lida,
    parar_digitando,
)

log = logging.getLogger(__name__)

# Digitação humana no celular: média de 36 palavras por minuto (estudo da Aalto/Cambridge/ETH,
# 2019), ou seja ~3 caracteres por segundo.
SEGUNDOS_BASE_DIGITANDO = 1.0
SEGUNDOS_POR_CARACTERE = 0.33
SEGUNDOS_MAXIMO_DIGITANDO = 15.0
MAXIMO_MENSAGENS = 3

_filas: dict[str, list[str]] = defaultdict(list)
_contagens: dict[str, asyncio.Task] = {}
_sessoes: dict[str, str] = {}
_travas: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_tarefas_ativas: set[asyncio.Task] = set()


def dividir_mensagens(texto: str) -> list[str]:
    pedacos = []
    for bloco in re.split(r"\n\s*\n", texto):
        bloco = _limpar_markdown(bloco)
        if bloco:
            pedacos.append(bloco)
    if len(pedacos) == 1:
        # O modelo nem sempre obedece à linha em branco: sem ela, quebra por frase.
        pedacos = _dividir_em_frases(pedacos[0])
    if len(pedacos) > MAXIMO_MENSAGENS:
        pedacos = pedacos[: MAXIMO_MENSAGENS - 1] + ["\n".join(pedacos[MAXIMO_MENSAGENS - 1 :])]
    return pedacos


def _dividir_em_frases(texto: str) -> list[str]:
    frases = re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÀ-Ú])", texto)
    return [f.strip() for f in frases if f.strip()]


def _limpar_markdown(texto: str) -> str:
    linhas = []
    for linha in texto.splitlines():
        linha = re.sub(r"^\s*#{1,6}\s+", "", linha)  # títulos
        linha = re.sub(r"^\s*>\s?", "", linha)  # citações
        linha = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", linha)  # marcadores de lista
        linha = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", linha)  # links
        linha = linha.replace("*", "").replace("`", "")
        linha = re.sub(r"(?<!\w)_+(.+?)_+(?!\w)", r"\1", linha)  # _itálico_
        linha = re.sub(r"~~(.+?)~~", r"\1", linha)  # ~~riscado~~
        linhas.append(linha.strip())
    return "\n".join(l for l in linhas if l).strip()


def _tempo_de_digitar(texto: str) -> float:
    return min(
        SEGUNDOS_BASE_DIGITANDO + SEGUNDOS_POR_CARACTERE * len(texto),
        SEGUNDOS_MAXIMO_DIGITANDO,
    )


def adicionar_mensagem(contato: str, texto: str, sessao: str = "default") -> None:
    _filas[contato].append(texto)
    _sessoes[contato] = sessao

    contagem_anterior = _contagens.get(contato)
    if contagem_anterior:
        contagem_anterior.cancel()

    tarefa = asyncio.create_task(_esperar_e_responder(contato))
    _contagens[contato] = tarefa
    _tarefas_ativas.add(tarefa)
    tarefa.add_done_callback(_tarefas_ativas.discard)


async def _esperar_e_responder(contato: str) -> None:
    await asyncio.sleep(BUFFER_SEGUNDOS)

    # Daqui pra frente a contagem acabou: tira ela do registro antes de qualquer await,
    # pra uma mensagem nova abrir uma contagem própria em vez de cancelar esta resposta.
    del _contagens[contato]
    mensagens = _filas.pop(contato, [])
    if not mensagens:
        return

    sessao = _sessoes.get(contato, "default")
    try:
        async with _travas[contato]:
            texto = "\n".join(mensagens)
            await _sinalizar(marcar_como_lida, contato, sessao)
            await _sinalizar(comecar_digitando, contato, sessao)
            inicio = time.monotonic()
            # O resumo da mídia roda junto com o agente, então não atrasa a resposta.
            resumo_pro_historico = asyncio.create_task(_texto_pro_historico(mensagens))
            try:
                resposta = await agent.run(texto, message_history=pegar_historico(contato))
                novas = _trocar_texto_do_cliente(
                    resposta.all_messages(), texto, await resumo_pro_historico
                )
                salvar_historico(contato, novas)
            except BaseException:
                resumo_pro_historico.cancel()
                await _sinalizar(parar_digitando, contato, sessao)
                raise

            partes = dividir_mensagens(resposta.output)
            for i, parte in enumerate(partes):
                if i > 0:
                    await _sinalizar(comecar_digitando, contato, sessao)
                    inicio = time.monotonic()
                # O tempo que o agente levou pensando já conta pra primeira mensagem.
                await asyncio.sleep(max(0.0, _tempo_de_digitar(parte) - (time.monotonic() - inicio)))
                await _sinalizar(parar_digitando, contato, sessao)
                await enviar_mensagem(contato, parte, sessao)
    except Exception:
        log.exception("Falha ao responder o contato %s", contato)


async def _texto_pro_historico(mensagens: list[str]) -> str:
    textos = await asyncio.gather(
        *(resumir_para_historico(m) if e_midia_longa(m) else _devolver(m) for m in mensagens)
    )
    return "\n".join(textos)


async def _devolver(texto: str) -> str:
    return texto


def _trocar_texto_do_cliente(
    mensagens: list[ModelMessage], texto_enviado: str, texto_pro_historico: str
) -> list[ModelMessage]:
    if texto_pro_historico == texto_enviado:
        return mensagens
    for mensagem in reversed(mensagens):
        if not isinstance(mensagem, ModelRequest):
            continue
        for parte in mensagem.parts:
            if isinstance(parte, UserPromptPart) and parte.content == texto_enviado:
                parte.content = texto_pro_historico
                return mensagens
    return mensagens


async def _sinalizar(funcao, contato: str, sessao: str) -> None:
    # "Lido" e "digitando" são enfeite: se falharem, a resposta sai do mesmo jeito.
    try:
        await funcao(contato, sessao)
    except Exception:
        log.warning("Falha em %s para %s", funcao.__name__, contato, exc_info=True)
