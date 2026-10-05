# PSAN Radar — Backend (FastAPI + GeoPandas + ReportLab)
FROM python:3.11-slim

# System libraries for C/GEOS dependencies (geopandas/shapely), plus curl for
# the compose healthcheck. APT cache purged to keep the image under 300MB.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgdal-dev \
        g++ \
        gcc \
        libgeos-dev \
        curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Application code
COPY *.py ./
COPY data ./data

# Run as a non-privileged user
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
