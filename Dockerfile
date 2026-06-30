# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

# Playwright needs a handful of system libraries to run headless Chromium.
# We install only what's needed rather than the full apt-get suggested set.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libdbus-1-3 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

# Don't run as root.
RUN useradd --create-home --shell /bin/bash agent \
    && chown -R agent:agent /app
USER agent

# Credentials, config, and resume are expected to be mounted/provided at
# runtime — see README.md and .env.example. They are NOT baked into the image.
ENTRYPOINT ["python", "-m", "src.naukri_agent.main"]
CMD ["run"]
