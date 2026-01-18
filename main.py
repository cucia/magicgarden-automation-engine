import json
import os
import random
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from modules.harvest import HarvestModule
from modules.sell import SellModule

# Force line-buffered output
sys.stdout = os.fdopen(sys.stdout.fileno(), "w", buffering=1)
sys.stderr = os.fdopen(sys.stderr.fileno(), "w", buffering=1)

# ============================================================
# ENV
# ============================================================
print("[INIT] Loading environment variables...", flush=True)
load_dotenv()
print("[INIT] Environment loaded", flush=True)

# ============================================================
# CONSTANTS
# ============================================================
GAME_URL = "https://magicgarden.gg"
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
WS_FRAME_THROTTLE = 5  # Process every 5th frame (reduce CPU)

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


def any_modules_enabled():
    return ENABLE_HARVEST or ENABLE_SELL or ENABLE_BUY or ENABLE_PLANT

def mark_activity():
    state["last_activity"] = time.time()

def idle_time():
    return time.time() - state["last_activity"]

# ============================================================
# WEBSOCKET HANDLING
# ============================================================
def attach_websocket_listeners(page):
    # Skip WS listeners if no modules are enabled
    if not any_modules_enabled():
        print("[WS] No modules enabled - skipping WebSocket listeners (CPU optimization)")
        return
    
    frame_counter = [0]  # counter for throttling
    
    def on_ws(ws):
        ws.on("framereceived", on_frame)
        ws.on("close", on_close)

    def on_close():
        state["connection_lost_at"] = time.time()
        print(f"[WS] Connection LOST at {time.strftime('%H:%M:%S')}")

    def on_frame(frame):
        # Throttle frame processing to reduce CPU
        frame_counter[0] += 1
        if frame_counter[0] % WS_FRAME_THROTTLE != 0:
            return
        
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
        print("[DEBUG] Adding stealth patch")
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
        """)

        # -------------------- OPEN GAME --------------------
        print("[DEBUG] Navigating to magicgarden.gg...")
        try:
            page.goto(GAME_URL, timeout=30000)
            print("✓ [INFO] Game page loaded successfully")
        except Exception as e:
            print(f"✗ [ERROR] Failed to load game: {e}")
            raise
        
        print("[DEBUG] Attaching WebSocket listeners...")
        attach_websocket_listeners(page)
        print("✓ [INFO] WebSocket listeners attached")

        print("[INFO] Game opened. Login once if needed.")

        # -------------------- MODULES --------------------
        harvest_module = HarvestModule(page, state, HARVEST_TIER)
        sell_module = SellModule(page, state)

        # ========================================================
        # MAIN LOOP
        # ========================================================
        loop_count = 0
        print(f"✓ [INFO] Starting main loop (ENGINE_TICK={ENGINE_TICK}, HARVEST={ENABLE_HARVEST}, SELL={ENABLE_SELL})")
        
        while True:
            loop_count += 1
            acted = False

            # ---------- AUTO RECONNECT ----------
            if AUTO_RECONNECT and state["connection_lost_at"]:
                elapsed = time.time() - state["connection_lost_at"]
                if elapsed >= RECONNECT_WAIT:
                    print(f"⚠ [RECONNECT] Connection lost for {elapsed:.1f}s. Reloading game...")
                    state["connection_lost_at"] = None
                    page.reload()
                    mark_activity()
                    time.sleep(5)
                    print("✓ [RECONNECT] Game reloaded")
                    continue
                elif loop_count % 20 == 0:
                    print(f"[RECONNECT] Waiting for reconnect... {elapsed:.1f}s / {RECONNECT_WAIT}s")
            
            # Log connection status
            if loop_count % 100 == 0:
                conn_status = "✓ CONNECTED" if not state["connection_lost_at"] else "✗ DISCONNECTED"
                print(f"[STATUS] Loop #{loop_count} | {conn_status} | Plots: {len(state['plots'])} | Inventory Full: {state['inventory_full']}")
            
            # ---------- SELL FIRST (BLOCKING) ----------
            if ENABLE_SELL:
                try:
                    if sell_module.run():
                        print(f"✓ [SELL] Selling items...")
                        mark_activity()
                        acted = True
                        continue
                except Exception as e:
                    print(f"✗ [ERROR] Sell module crashed: {e}")

            # ---------- HARVEST ----------
            if ENABLE_HARVEST:
                try:
                    if harvest_module.run():
                        if loop_count % 10 == 0:
                            print(f"✓ [HARVEST] Harvesting plots... (Loop #{loop_count})")
                        mark_activity()
                        acted = True
                except Exception as e:
                    print(f"✗ [ERROR] Harvest module crashed: {e}")

            # ---------- IDLE KEEP ALIVE ----------
            if not acted and idle_time() > IDLE_THRESHOLD:
                print(f"[IDLE] No action for {idle_time():.1f}s. Sending keep-alive ping...")
                try:
                    page.keyboard.press("ArrowLeft")
                    page.wait_for_timeout(150)
                    page.keyboard.press("ArrowRight")
                    mark_activity()
                except Exception as e:
                    print(f"✗ [ERROR] Keep-alive failed: {e}")
            
            if loop_count % 200 == 0:
                print(f"[LOOP] Running... (Loop #{loop_count} | Idle for {idle_time():.1f}s)")

            time.sleep(ENGINE_TICK + random.uniform(0, 0.05))

# ============================================================
if __name__ == "__main__":
    try:
        print("[MAIN] Starting automation engine...", flush=True)
        main()
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down gracefully...", flush=True)
    except Exception as e:
        print(f"✗ [FATAL] Unhandled error: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
