FROM mcr.microsoft.com/playwright/python:v1.57.0-jammy

# -------------------- ENV --------------------
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV DISPLAY=:99

# -------------------- WORKDIR --------------------
WORKDIR /app

# -------------------- COPY PROJECT --------------------
COPY . /app

# -------------------- PYTHON DEPS (CRITICAL FIX) --------------------
# Use python3 -m pip to guarantee correct site-packages
RUN python3 -m pip install --no-cache-dir \
    playwright==1.57.0 \
    python-dotenv

# -------------------- GUI + noVNC --------------------
RUN apt-get update && apt-get install -y \
    tzdata \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    && rm -rf /var/lib/apt/lists/*

# -------------------- EXPOSE noVNC --------------------
EXPOSE 6080

# -------------------- STARTUP --------------------
CMD rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 && \
    Xvfb :99 -screen 0 1280x720x16 & \
    sleep 2 && \
    x11vnc -display :99 -nopw -forever -shared -noxdamage -nowf -nowcr & \
    websockify --web=/usr/share/novnc/ 6080 localhost:5900 & \
    python3 main.py
# -------------------- END --------------------