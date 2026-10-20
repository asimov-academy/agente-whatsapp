# Chat de teste no terminal para conversar com o agente sem WhatsApp. Peça: código.
import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from app.agent import agent  # noqa: E402
from app.ritmo import MENSAGEM_REINICIADO, dividir_mensagens, e_comando_reiniciar  # noqa: E402
from app.humano import (  # noqa: E402
    Contexto,
    anexar_mensagem_do_cliente,
    e_joinha,
    pausa_ativa,
    processar_joinha_da_equipe,
    processar_mensagem_da_equipe,
    retomar,
)
from app.memory import apagar_historico, pegar_historico, salvar_historico  # noqa: E402

contato = "pedro"
print(f"Falando como: {contato}")

while True:
    try:
        mensagem = input(f"{contato}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        break
    if mensagem.lower() == "sair":
        break
    if e_comando_reiniciar(mensagem):
        apagar_historico(contato)
        print(f"Agente: {MENSAGEM_REINICIADO}")
        continue
    if mensagem.startswith("/contato"):
        novo = mensagem.removeprefix("/contato").strip()
        if novo:
            contato = novo
            print(f"Agora você está falando como: {contato}")
        else:
            print("Use: /contato nome")
        continue
    if mensagem.lower() == "/retomar":
        print("[Duda de volta neste contato]" if retomar(contato) else "[este contato não estava pausado]")
        continue
    if mensagem.startswith("/equipe"):
        # Simula a equipe pelo celular da barbearia. "/equipe 👍" simula o 👍 numa mensagem da conversa.
        texto_da_equipe = mensagem.removeprefix("/equipe").strip()
        if not texto_da_equipe:
            print("Use: /equipe texto  (ou /equipe 👍 pra devolver a conversa pra Duda)")
        elif e_joinha(texto_da_equipe):
            print(
                "[👍: a Duda voltou. Ela não manda nada: espera a próxima mensagem do cliente]"
                if processar_joinha_da_equipe(contato) == "voltou"
                else "[👍: este contato não estava pausado]"
            )
        else:
            print({
                "registrada": "[mensagem da equipe salva no histórico; a Duda ficou pausada neste contato]",
                "ignorada": "[ignorada: este contato nunca falou com a Duda, então não vira histórico]",
            }[processar_mensagem_da_equipe(contato, texto_da_equipe)])
        continue
    if pausa_ativa(contato):
        anexar_mensagem_do_cliente(contato, mensagem)
        print("[Duda pausada neste contato: a equipe responde. Mensagem salva no histórico. /retomar traz a Duda de volta]")
        continue
    try:
        resposta = agent.run_sync(
            mensagem,
            message_history=pegar_historico(contato),
            deps=Contexto(contato=contato, terminal=True),
        )
    except KeyboardInterrupt:
        print("\n[interrompido. Manda a mensagem de novo ou digita sair.]")
        continue
    except Exception as erro:
        print(f"[erro ao falar com o modelo: {type(erro).__name__}. Manda a mensagem de novo.]")
        continue
    salvar_historico(contato, resposta.all_messages())
    for parte in dividir_mensagens(resposta.output):
        print(f"Agente: {parte}")
    uso = resposta.usage
    print(f"[tokens: {uso.input_tokens} de entrada, {uso.output_tokens} de saída]")
