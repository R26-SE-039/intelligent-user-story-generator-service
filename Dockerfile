FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by psycopg2 and azure-cognitiveservices-speech
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install the CPU-only torch wheel first (this box has no GPU) so pip doesn't
# pull the ~2.7 GB CUDA build; it satisfies requirements.txt's torch>=2.0.0.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8001

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
