FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /app/logs /app/models_cache /app/data

# Copy and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=1000 --retries=5 -r requirements.txt

# Copy application
COPY src/ ./src/
COPY data/ ./data/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FASTEMBED_CACHE_DIR=/app/models_cache
ENV ENVIRONMENT=production

# Expose port
EXPOSE 8000

# Run with Render's PORT
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --log-level info"]