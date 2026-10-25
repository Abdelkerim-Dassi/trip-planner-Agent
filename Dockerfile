# Voyagent web app + MCP server.
# Works on Render's free plan, Hugging Face Spaces and any container host.
# Hosts that set PORT (e.g. Render) override the 7860 default.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    PORT=7860

# Run as an unprivileged user (uid 1000, as Hugging Face Spaces expects).
RUN useradd -m -u 1000 voyagent
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=voyagent src ./src
RUN mkdir -p /app/data && chown voyagent /app/data
USER voyagent

EXPOSE 7860
CMD ["python", "-m", "voyagent.web"]
