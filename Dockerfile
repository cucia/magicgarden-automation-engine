FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

# -------------------- ENV --------------------
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# -------------------- WORKDIR --------------------
WORKDIR /app

# -------------------- SYSTEM DEPS (GUI + noVNC) --------------------
RUN apt-get update && apt-get install -y \
    tzdata \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

# -------------------- COPY PROJECT --------------------
COPY . /app

# -------------------- PYTHON DEPS (ONCE, CLEAN) --------------------
RUN python3 -m pip install --no-cache-dir \
    playwright==1.57.0 \
    python-dotenv

# -------------------- EXPOSE noVNC --------------------
EXPOSE 6080

# -------------------- ENTRYPOINT --------------------
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
