FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
RUN python -c "from kokoro import KPipeline; KPipeline(lang_code='a'); print('Kokoro model cache primed')"

# espeak-ng is optional — used by misaki as a fallback for out-of-vocabulary
# words. Install it if apt repos are reachable, skip gracefully otherwise.
RUN apt-get update && apt-get install -y --no-install-recommends espeak-ng \
    && rm -rf /var/lib/apt/lists/* \
    || echo "espeak-ng install skipped (apt unreachable)"

COPY app ./app

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
