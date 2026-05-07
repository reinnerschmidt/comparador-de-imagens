# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# Dependências do sistema para OpenCV e Matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala dependências Python primeiro (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código
COPY . .

# Cria diretórios de dados persistentes
RUN mkdir -p data/inspections data/reports data/comparisons

# Expõe a porta (Railway injeta PORT no env)
EXPOSE 5051

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-5051}/health')"

CMD ["python", "scripts/mobile_app/server.py"]
