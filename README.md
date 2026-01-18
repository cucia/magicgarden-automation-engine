# MagicGarden Automation Bot (Infrastructure Base)

This repository contains the **infrastructure and core engine** for a MagicGarden automation bot.

At this stage, the project focuses on:
- Dockerized browser automation
- Persistent login sessions
- Stealth Playwright setup
- WebSocket state ingestion
- Engine loop & reconnect logic

> ⚠️ Game logic modules (harvest / buy / sell / plant) are intentionally **not included yet**.  
> This repository represents a **stable automation foundation**.

---

## ✨ Features (Current Stage)

- 🐳 **Dockerized environment**
- 🖥️ **Visible browser via noVNC**
- 🔐 **Persistent login session** (no re-login after restart)
- 🕵️ **Stealth Playwright patches**
- 🔌 **WebSocket listener for real-time game state**
- 🔁 **Auto-reconnect when session is kicked**
- 💤 **Idle keep-alive to prevent disconnects**
- ⚙️ Fully configurable via `.env`

---

## 🗂️ Project Structure