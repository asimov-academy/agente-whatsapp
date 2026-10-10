# Define o agente PydanticAI, rodando num modelo via OpenRouter, com o prompt da Duda e a data de hoje. Peça: LLM.
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent

CAMINHO_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"

agent = Agent(
    "openrouter:openai/gpt-6-luna",
    instructions=CAMINHO_PROMPT.read_text(encoding="utf-8"),
)

DIAS_DA_SEMANA = [
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
]  # fmt: skip
MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


@agent.instructions
def data_e_hora_de_agora() -> str:
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    return (
        f"Agora é {DIAS_DA_SEMANA[agora.weekday()]}, {agora.day} de {MESES[agora.month - 1]} "
        f"de {agora.year}, {agora:%H:%M} (horário de São Paulo). "
        "Usa isso para entender \"hoje\", \"amanhã\" e \"sábado que vem\"."
    )
