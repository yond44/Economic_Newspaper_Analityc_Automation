FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Use faster mirror
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# Install problematic package first with longer timeout
RUN pip install --no-cache-dir --timeout=1000 --retries=10 llama-index-llms-groq

# Copy requirements and install rest
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=1000 --use-deprecated=legacy-resolver -r requirements.txt

# Copy application code (NO .env!)
COPY src/ ./src/
COPY data/ ./data/

# Create directories for logs
RUN mkdir -p /app/logs

# Expose port - Render uses PORT environment variable
EXPOSE 8000

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]