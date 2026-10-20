# Junta as mensagens picadas de cada contato e responde só quando ele para de falar. Peça: código.
import asyncio
import logging
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from app.config import BUFFER_SEGUNDOS  # isort: skip  (carrega o .env antes do agente)
from app.agent import agent
from app.humano import Contexto, anexar_mensagem_do_cliente, pausa_ativa
from app.memory import apagar_historico, pegar_historico, salvar_historico, trava_do_contato
from app.midia import e_midia_longa, resumir_para_historico
from app.whatsapp import (
    comecar_digitando,
    enviar_mensagem,
    marcar_como_lida,
    parar_digitando,
)

log = logging.getLogger(__name__)

# Tempo de "digitando" de cada mensagem: 1 s mais 0,03 s por caractere, entre 1,5 e 4 segundos.
SEGUNDOS_BASE_DIGITANDO = 1.0
SEGUNDOS_POR_CARACTERE = 0.03
SEGUNDOS_MINIMO_DIGITANDO = 1.5
SEGUNDOS_MAXIMO_DIGITANDO = 4.0
SEGUNDOS_PARA_LER = 1.0  # a mensagem do cliente é marcada como lida 1 s depois de chegar
SEGUNDOS_ENTRE_MENSAGENS = 0.5  # depois de enviar, o "digitando" some: espera antes de ligar de novo
SEGUNDOS_PARA_RENOVAR_DIGITANDO = 5.0  # o WhatsApp apaga o "digitando" sozinho depois de uns segundos
MAXIMO_MENSAGENS = 3

_filas: dict[str, list[str]] = defaultdict(list)
_contagens: dict[str, asyncio.Task] = {}
_sessoes: dict[str, str] = {}
_ultima_mensagem: dict[str, float] = {}  # só pra medir o tempo de resposta
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
    tempo = SEGUNDOS_BASE_DIGITANDO + SEGUNDOS_POR_CARACTERE * len(texto)
    return min(max(tempo, SEGUNDOS_MINIMO_DIGITANDO), SEGUNDOS_MAXIMO_DIGITANDO)


def agendar_leitura(contato: str, sessao: str = "default") -> None:
    """Marca a conversa como lida 1 segundo depois que a mensagem chega, sem esperar o buffer."""
    tarefa = asyncio.create_task(_marcar_como_lida_depois(contato, sessao))
    _tarefas_ativas.add(tarefa)
    tarefa.add_done_callback(_tarefas_ativas.discard)


async def _marcar_como_lida_depois(contato: str, sessao: str) -> None:
    await asyncio.sleep(SEGUNDOS_PARA_LER)
    if pausa_ativa(contato):
        return  # contato com um humano: a Duda não marca nada
    await _sinalizar(marcar_como_lida, contato, sessao)


@asynccontextmanager
async def _digitando(contato: str, sessao: str):
    """Mostra o "digitando" enquanto o bloco roda e desliga ao sair, mesmo se der erro.

    Renova o sinal a cada 5 segundos, porque o WhatsApp apaga o "digitando" sozinho. Não marca a
    sessão como online: isso faz o celular da barbearia parar de receber notificação.
    """
    await _sinalizar(comecar_digitando, contato, sessao)
    renovador = asyncio.create_task(_renovar_digitando(contato, sessao))
    try:
        yield
    finally:
        renovador.cancel()
        await asyncio.gather(renovador, return_exceptions=True)
        await _sinalizar(parar_digitando, contato, sessao)


async def _renovar_digitando(contato: str, sessao: str) -> None:
    while True:
        await asyncio.sleep(SEGUNDOS_PARA_RENOVAR_DIGITANDO)
        await _sinalizar(comecar_digitando, contato, sessao)


COMANDO_REINICIAR = "#reset"
MENSAGEM_REINICIADO = "Agente Reiniciado!"


def e_comando_reiniciar(texto: str) -> bool:
    return texto.strip().lower() == COMANDO_REINICIAR


def reiniciar_em_segundo_plano(contato: str, sessao: str = "default") -> None:
    tarefa = asyncio.create_task(reiniciar_conversa(contato, sessao))
    _tarefas_ativas.add(tarefa)
    tarefa.add_done_callback(_tarefas_ativas.discard)


async def reiniciar_conversa(contato: str, sessao: str = "default") -> None:
    """#reset: apaga o histórico (e a pausa) daquele contato e avisa. O comando não vai pro agente."""
    contagem = _contagens.pop(contato, None)
    if contagem:
        contagem.cancel()  # o que estava esperando no buffer não é mais respondido
    _filas.pop(contato, None)
    try:
        async with trava_do_contato(contato):  # se a Duda está no meio de uma resposta, espera ela acabar
            apagar_historico(contato)
        await enviar_mensagem(contato, MENSAGEM_REINICIADO, sessao)
    except Exception:
        log.exception("Falha ao reiniciar a conversa de %s", contato)


def adicionar_mensagem(contato: str, texto: str, sessao: str = "default") -> None:
    _filas[contato].append(texto)
    _sessoes[contato] = sessao
    _ultima_mensagem[contato] = time.monotonic()

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
    # Medição (só pro log do fim): da última mensagem do cliente até a última da Duda.
    t_ultima_mensagem = _ultima_mensagem.get(contato, time.monotonic())
    espera = time.monotonic() - t_ultima_mensagem
    t_fila = time.monotonic()
    try:
        async with trava_do_contato(contato):
            fila = time.monotonic() - t_fila
            if pausa_ativa(contato):
                # Contato com um humano: a Duda não responde nada (nem lido, nem digitando),
                # mas a conversa continua no histórico pra ela saber o que houve quando voltar.
                # (pausa_ativa já tirou a pausa se passou de PAUSA_MINUTOS: aí ela responde normal.)
                anexar_mensagem_do_cliente(contato, await _texto_pro_historico(mensagens))
                return
            texto = "\n".join(mensagens)
            # O resumo da mídia roda junto com o agente, então não atrasa a resposta.
            resumo_pro_historico = asyncio.create_task(_texto_pro_historico(mensagens))
            digitando, envio = [], 0.0
            try:
                t_digitando = time.monotonic()
                async with _digitando(contato, sessao):  # desliga o "digitando" mesmo se der erro
                    inicio = time.monotonic()
                    sinais = inicio - t_digitando
                    t_agente = time.monotonic()
                    resposta = await agent.run(
                        texto,
                        message_history=pegar_historico(contato),
                        deps=Contexto(contato=contato, sessao=sessao),
                    )
                    agente = time.monotonic() - t_agente
                    t_resumo = time.monotonic()
                    texto_pro_historico = await resumo_pro_historico
                    resumo_da_midia = time.monotonic() - t_resumo
                    novas = _trocar_texto_do_cliente(resposta.all_messages(), texto, texto_pro_historico)
                    salvar_historico(contato, novas)

                    partes = dividir_mensagens(resposta.output)
                    if partes:
                        # O tempo que o agente levou pensando já conta pra primeira mensagem.
                        await asyncio.sleep(
                            max(0.0, _tempo_de_digitar(partes[0]) - (time.monotonic() - inicio))
                        )
                digitando.append(time.monotonic() - t_digitando)
            except BaseException:
                resumo_pro_historico.cancel()
                raise

            for i, parte in enumerate(partes):
                if i > 0:
                    # O WhatsApp apaga o "digitando" quando uma mensagem é enviada.
                    await asyncio.sleep(SEGUNDOS_ENTRE_MENSAGENS)
                    t_digitando = time.monotonic()
                    async with _digitando(contato, sessao):
                        await asyncio.sleep(_tempo_de_digitar(parte))
                    digitando.append(time.monotonic() - t_digitando)
                t_envio = time.monotonic()
                await enviar_mensagem(contato, parte, sessao)
                envio += time.monotonic() - t_envio
            _registrar_tempos(
                contato, espera, fila, sinais, agente, resumo_da_midia, digitando, envio,
                total=time.monotonic() - t_ultima_mensagem,
            )
    except Exception:
        log.exception("Falha ao responder o contato %s", contato)


def _registrar_tempos(contato, espera, fila, sinais, agente, resumo_da_midia, digitando, envio, total) -> None:
    """Uma linha por resposta, pra ver onde o tempo vai. Só mede: não muda nada no comportamento.

    espera: o buffer, esperando o cliente parar de escrever. fila: esperando a resposta anterior
    do mesmo contato acabar. sinais: a chamada ao WAHA que liga o "digitando". agente: o modelo
    gerando a resposta. resumo_da_midia: sobra do resumo de imagem/documento depois do agente.
    digitando: por mensagem, do "digitando" aparecer até parar (na primeira, o agente está dentro).
    envio: as chamadas ao WAHA que mandam as mensagens. total: da última mensagem do cliente até
    a última da Duda.
    """
    lista = ", ".join(f"{d:.1f}s" for d in digitando)
    log.info(
        "Tempos de %s: espera=%.1fs fila=%.1fs sinais=%.1fs agente=%.1fs resumo_da_midia=%.1fs "
        "digitando=[%s] envio=%.1fs total=%.1fs",
        f"{contato[:6]}...{contato[-6:]}", espera, fila, sinais, agente, resumo_da_midia, lista, envio, total,
    )


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
