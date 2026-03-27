FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3.10-venv \
    python3.10-dev \
    git \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set python3 as default
RUN ln -s /usr/bin/python3.10 /usr/bin/python

COPY requirements.txt .

# Install Python requirements
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu118

# diffusers 0.27 expects huggingface_hub APIs removed in newer releases.
RUN pip install --no-cache-dir "huggingface_hub==0.20.2"


# Provide a script to download weights (can be run on start or built into image)
COPY scripts/download_weights.py ./scripts/

# The application code
COPY app ./app

EXPOSE 8020

# Run weight downloader (if empty) then start the FastAPI server
CMD python scripts/download_weights.py && uvicorn app.main:app --host 0.0.0.0 --port 8020
