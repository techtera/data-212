FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Security: run as non-root
RUN useradd -m appuser
USER appuser

# Cloud Run injects PORT env var
ENV PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
