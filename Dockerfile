# Voyagent web app + MCP server.
# Works on Hugging Face Spaces (Docker SDK, free CPU tier) and any container host.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=7860

# Hugging Face Spaces runs containers as user 1000.
RUN useradd -m -u 1000 voyagent
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=voyagent src ./src
RUN mkdir -p /app/data && chown voyagent /app/data
USER voyagent

EXPOSE 7860
CMD ["python", "-m", "voyagent.web"]
