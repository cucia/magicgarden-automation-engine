import os
import time
import json
import random
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from modules.harvest import HarvestModule
from modules.sell import SellModule

# ============================================================
# ENV
# ============================================================
load_dotenv()

ENGINE_TICK = float(os.getenv("ENGINE_TICK", 0.2))
IDLE_THRESHOLD = float(os.getenv("IDLE_THRESHOLD", 15))

PERSIST_SESSION = os.getenv("PERSIST_SESSION", "false") == "true"
PROFILE_DIR = os.getenv("BROWSER_PROFILE_DIR", "/app/browser-profile")

AUTO_RECONNECT = os.getenv("AUTO_RECONNECT", "true") == "true"
RECONNECT_WAIT = int(os.getenv("RECONNECT_WAIT_MINUTES", "5")) * 60

ENABLE_HARVEST = os.getenv("ENABLE_HARVEST", "false") == "true"
ENABLE_BUY = os.getenv("ENABLE_BUY", "false") == "true"
ENABLE_SELL = os.getenv("ENABLE_SELL", "false") == "true"
ENABLE_PLANT = os.getenv("ENABLE_PLANT", "false") == "true"

HARVEST_TIER = os.getenv("HARVEST_TIER", "S")

BUY_ALLOWED_SEEDS = [
    s.strip() for s in os.getenv("BUY_ALLOWED_SEEDS", "").split(",") if s.strip()
]

DEBUG_WS = os.getenv("DEBUG_WS", "false") == "true"

# ============================================================
# STATE (SINGLE SOURCE OF TRUTH)
# ============================================================
state = {
    "last_activity": time.time(),

    # WS driven
    "plots": {},                 # plot_id -> plot_state
    "inventory_full": False,

    # shop
    "seed_restock_prev": None,
    "seed_restock_now": None,
    "seed_stock_up": False,

    # connection
    "connection_lost_at": None,

    # harvest resume
    "harvest_cursor": 0,
}

def mark_activity():
    state["last_activity"] = time.time()

def idle_time():
    return time.time() - state["last_activity"]

# ============================================================
# WEBSOCKET HANDLING
# ============================================================
def attach_websocket_listeners(page):
    def on_ws(ws):
        ws.on("framereceived", on_frame)
        ws.on("close", on_close)

    def on_close():
        state["connection_lost_at"] = time.time()
        print("[WS] Connection closed")

    def on_frame(frame):
        try:
            data = json.loads(frame.payload)
        except Exception:
            return

        if data.get("type") != "PartialState":
            return

        for patch in data.get("patches", []):
            path = patch.get("path")
            value = patch.get("value")

            # ---------------- SHOP RESTOCK ----------------
            if path == "/child/data/shops/seed/secondsUntilRestock":
                prev = state["seed_restock_now"]
                curr = value
                state["seed_restock_prev"] = prev
                state["seed_restock_now"] = curr

                if prev is not None and prev <= 1 and curr > prev:
                    state["seed_stock_up"] = True
                    if DEBUG_WS:
                        print("[WS] Seed shop restocked")

            # ---------------- INVENTORY FULL ----------------
            if path == "/child/data/inventory/isFull" and value is True:
                state["inventory_full"] = True
                if DEBUG_WS:
                    print("[WS] Inventory full")

            # ---------------- PLOT STATE ----------------
            if path and path.startswith("/child/data/garden/plots/"):
                plot_id = path.split("/")[-1]
                state["plots"][plot_id] = value

    page.on("websocket", on_ws)

# ============================================================
# MAIN
# ============================================================
def main():
    with sync_playwright() as p:

        # -------------------- BROWSER OPTIONS --------------------
        launch_args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--start-maximized",
        ]

        context_options = dict(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )

        # -------------------- CONTEXT --------------------
        if PERSIST_SESSION:
            context = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
                args=launch_args,
                **context_options,
            )
            page = context.pages[0] if context.pages else context.new_page()
            print("[INFO] Persistent session enabled")
        else:
            browser = p.chromium.launch(headless=False, args=launch_args)
            context = browser.new_context(**context_options)
            page = context.new_page()
            print("[INFO] Non-persistent session")

        # -------------------- STEALTH PATCH --------------------
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        """)

        # -------------------- OPEN GAME --------------------
        page.goto("https://magicgarden.gg")
        attach_websocket_listeners(page)

        print("[INFO] Game opened. Login once if needed.")

        # -------------------- MODULES --------------------
        harvest_module = HarvestModule(page, state, HARVEST_TIER)
        sell_module = SellModule(page, state)

        # ========================================================
        # MAIN LOOP
        # ========================================================
        while True:
            acted = False

            # ---------- AUTO RECONNECT ----------
            if AUTO_RECONNECT and state["connection_lost_at"]:
                elapsed = time.time() - state["connection_lost_at"]
                if elapsed >= RECONNECT_WAIT:
                    print("[RECONNECT] Reloading game")
                    state["connection_lost_at"] = None
                    page.reload()
                    mark_activity()
                    time.sleep(5)
                    continue

            # ---------- SELL FIRST (BLOCKING) ----------
            if ENABLE_SELL and sell_module.run():
                mark_activity()
                acted = True
                continue  # resume harvest from same cursor

            # ---------- HARVEST ----------
            if ENABLE_HARVEST and harvest_module.run():
                mark_activity()
                acted = True

            # ---------- IDLE KEEP ALIVE ----------
            if not acted and idle_time() > IDLE_THRESHOLD:
                page.keyboard.press("ArrowLeft")
                page.wait_for_timeout(150)
                page.keyboard.press("ArrowRight")
                mark_activity()

            time.sleep(ENGINE_TICK + random.uniform(0, 0.05))

# ============================================================
if __name__ == "__main__":
    main()
