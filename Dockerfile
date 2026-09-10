FROM python:3.11-slim

# Instalar dependências do sistema necessárias para processamento de vídeo (ffmpeg, opencv)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependências do Python
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copiar o restante do código
COPY . .
