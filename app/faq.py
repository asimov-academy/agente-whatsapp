# Baixa a FAQ da planilha do Google Planilhas e entrega pronta pro agente. Peça: código.
import csv
import io
import logging
import os
import threading
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

CACHE_SEGUNDOS = 60
COLUNAS = ("categoria", "pergunta", "resposta")
COPIA_LOCAL = Path(__file__).resolve().parent.parent / "documentos" / "faq.csv"

_trava = threading.Lock()
_cache: dict = {"quando": None, "linhas": None}  # "linhas": a última FAQ boa, na memória


def _ler_linhas(conteudo_csv: str) -> list[dict] | None:
    """Devolve as linhas da FAQ, ou None se o CSV não tiver as colunas esperadas."""
    leitor = csv.DictReader(io.StringIO(conteudo_csv))
    colunas = {(c or "").strip().lower() for c in (leitor.fieldnames or [])}
    if not set(COLUNAS) <= colunas:
        return None
    linhas = []
    for bruta in leitor:
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in bruta.items()}
        if linha.get("pergunta") or linha.get("resposta"):
            linhas.append({c: linha.get(c, "") for c in COLUNAS})
    return linhas


def _baixar_csv(url: str) -> str:
    resposta = httpx.get(url, timeout=10, follow_redirects=True)
    resposta.raise_for_status()
    return resposta.content.decode("utf-8-sig")


def _ler_copia_local() -> list[dict] | None:
    if not COPIA_LOCAL.exists():
        return None
    return _ler_linhas(COPIA_LOCAL.read_text(encoding="utf-8-sig"))


def _carregar() -> list[dict] | None:
    url = os.environ.get("FAQ_PLANILHA_URL", "").strip()
    if url:
        try:
            conteudo = _baixar_csv(url)
            linhas = _ler_linhas(conteudo)
            if linhas is not None:
                COPIA_LOCAL.parent.mkdir(parents=True, exist_ok=True)
                COPIA_LOCAL.write_text(conteudo, encoding="utf-8")
                return linhas
            log.warning(
                "A planilha da FAQ veio sem as colunas %s (link errado ou planilha fechada?). "
                "Usando a última versão boa.",
                ", ".join(COLUNAS),
            )
        except Exception as erro:
            log.warning("Não consegui baixar a FAQ (%s). Usando a última versão boa.", erro)
    else:
        log.warning("FAQ_PLANILHA_URL não está definida. Usando a última versão boa.")

    # Download falhou: a última boa da memória, e se não houver, a cópia salva em documentos/.
    if _cache["linhas"] is not None:
        return _cache["linhas"]
    return _ler_copia_local()


def carregar_faq() -> list[dict] | None:
    """FAQ atual. Com a FAQ já na memória, nunca espera o download: devolve a que tem e, quando o
    cache vence (60 s), baixa a nova em segundo plano. Só a primeira vez, sem FAQ nenhuma na
    memória, espera o download (ou usa a cópia em documentos/)."""
    with _trava:
        vencido = _cache["quando"] is None or time.monotonic() - _cache["quando"] >= CACHE_SEGUNDOS
        if not vencido:
            return _cache["linhas"]
        if _cache["linhas"] is not None:
            # Marca já, pra não disparar outro download enquanto este não termina.
            _cache["quando"] = time.monotonic()
            threading.Thread(target=_atualizar_em_segundo_plano, daemon=True).start()
            return _cache["linhas"]
        linhas = _carregar()  # primeira vez: não tem o que devolver, então espera
        _cache["quando"] = time.monotonic()  # mesmo se falhar: só tenta de novo em 60 segundos
        if linhas is not None:
            _cache["linhas"] = linhas
        return linhas


def _atualizar_em_segundo_plano() -> None:
    linhas = _carregar()  # a rede roda sem segurar a trava: as respostas não esperam por ela
    with _trava:
        if linhas is not None:
            _cache["linhas"] = linhas


def texto_da_faq() -> str:
    """A FAQ em texto, agrupada por categoria. Vazio se não houver FAQ nenhuma."""
    linhas = carregar_faq()
    if not linhas:
        return ""
    por_categoria: dict[str, list[dict]] = {}
    for linha in linhas:
        por_categoria.setdefault(linha["categoria"] or "geral", []).append(linha)
    blocos = []
    for categoria, itens in por_categoria.items():
        corpo = "\n".join(f"P: {i['pergunta']}\nR: {i['resposta']}" for i in itens)
        blocos.append(f"[{categoria}]\n{corpo}")
    return "\n\n".join(blocos)
