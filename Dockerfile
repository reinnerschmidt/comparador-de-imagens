FROM python:3.12-slim

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

# CMD usa shell form para expandir $PORT corretamente
CMD cd /app && PYTHONPATH=src gunicorn \
    --bind 0.0.0.0:${PORT:-5051} \
    --timeout 180 \
    --workers 1 \
    --preload \
    scripts.mobile_app.server:app
