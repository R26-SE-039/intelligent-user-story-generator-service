FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by psycopg2 and azure-cognitiveservices-speech
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install CPU-optimized PyTorch (saves 4.5GB disk space vs default CUDA torch)
RUN pip install --no-cache-dir torch --extra-index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
