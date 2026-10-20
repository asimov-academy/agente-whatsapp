# Define o agente PydanticAI, rodando num modelo via OpenRouter, com o prompt da Duda, a FAQ, a data de hoje e a ferramenta de chamar um humano. Peça: LLM.
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_ai import Agent, RunContext
from pydantic_ai.settings import ModelSettings

from app.faq import texto_da_faq
from app.humano import Contexto, chamar_humano_agora

CAMINHO_PROMPT = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"

agent = Agent(
    "openrouter:openai/gpt-6-luna",
    deps_type=Contexto,
    instructions=CAMINHO_PROMPT.read_text(encoding="utf-8"),
    # Sem isso, uma chamada que fica pendurada espera até 10 minutos (o padrão do cliente).
    model_settings=ModelSettings(timeout=30),
)



@agent.instructions
def faq_da_barbearia() -> str:
    faq = texto_da_faq()
    if not faq:
        return (
            "A FAQ da barbearia está indisponível agora. Não responde preço, horário, endereço "
            "nem regras: diz que vai confirmar com a equipe e retorna."
        )
    return (
        "A FAQ abaixo é material de consulta. Pra preço, horário, endereço e regras da barbearia, "
        "tu só usa as informações que estão nela. As respostas da FAQ são a informação certa, não a "
        "frase pronta: tu usa o dado e responde no teu jeito. Se a resposta não estiver na FAQ, "
        "não inventa: "
        "diz que vai confirmar com a equipe.\n\n"
        f"<faq>\n{faq}\n</faq>"
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


DESCRICAO_CHAMAR_HUMANO = (
    "Usa quando o cliente pedir pra falar com uma pessoa, quando a pergunta não estiver na FAQ, "
    "quando o cliente estiver irritado ou reclamando, ou quando o assunto for algo que tu não deve "
    "resolver, como problema com pagamento. Não usa pra pergunta que a FAQ responde."
)


@agent.tool(description=DESCRICAO_CHAMAR_HUMANO)
async def chamar_humano(ctx: RunContext[Contexto], motivo: str, resumo: str) -> str:
    """Passa a vez pra um humano da equipe.

    Args:
        motivo: Por que a vez passa pra equipe, por exemplo: pediu uma pessoa, pergunta fora da FAQ, reclamação.
        resumo: O que o cliente quer, em uma ou duas frases.
    """
    return await chamar_humano_agora(ctx.deps, motivo, resumo)
