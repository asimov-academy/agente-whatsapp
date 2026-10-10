# Chat de teste no terminal para conversar com o agente sem WhatsApp. Peça: código.
import os

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from app.agent import agent  # noqa: E402
from app.ritmo import dividir_mensagens  # noqa: E402
from app.memory import pegar_historico, salvar_historico  # noqa: E402

contato = "pedro"
print(f"Falando como: {contato}")

while True:
    mensagem = input(f"{contato}: ").strip()
    if mensagem.lower() == "sair":
        break
    if mensagem.startswith("/contato"):
        novo = mensagem.removeprefix("/contato").strip()
        if novo:
            contato = novo
            print(f"Agora você está falando como: {contato}")
        else:
            print("Use: /contato nome")
        continue
    resposta = agent.run_sync(mensagem, message_history=pegar_historico(contato))
    salvar_historico(contato, resposta.all_messages())
    for parte in dividir_mensagens(resposta.output):
        print(f"Agente: {parte}")
