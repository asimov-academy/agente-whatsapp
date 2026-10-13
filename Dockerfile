# Imagem da Duda: o servidor do agente (código + LLM) pronto pra rodar em container.
FROM python:3.12-slim

# A Duda usa o fuso de São Paulo pra saber que dia é hoje, e a imagem slim não traz o tzdata.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
