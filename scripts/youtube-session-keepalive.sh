#!/bin/bash
# YouTube session keepalive for MeTube.
# Cada 6h abre YouTube con Chromium headless usando el perfil persistente,
# simula actividad humana (scroll + click), y reexporta cookies a MeTube.
#
# Si YouTube devuelve CAPTCHA o "verify you're not a bot", loguea y avisa.
# Si las cookies cambiaron materialmente, reinicia MeTube para que las recargue.

set -euo pipefail

# --- Config ---
LOG="/var/log/metube/youtube-keepalive.log"
STATE_DIR="/root/metube/state"
CHROME_PROFILE="$STATE_DIR/chrome-profile"
COOKIES_OUT="$STATE_DIR/cookies.txt"
METUBE_SERVICE="metube.service"
XVFB_DISPLAY=":99"
CHROME_REMOTE_PORT="9222"

# User-Agent que coincide con lo que yt-dlp espera (mweb)
USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

mkdir -p "$STATE_DIR" "$(dirname "$LOG")" "$CHROME_PROFILE"

log() {
    echo "[$(TZ=America/Lima date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"
}

# Hash actual de cookies (para detectar cambios)
COOKIES_HASH_BEFORE=""
if [ -f "$COOKIES_OUT" ]; then
    COOKIES_HASH_BEFORE=$(sha256sum "$COOKIES_OUT" | cut -d' ' -f1)
fi

log "=== Keepalive START (hash before: ${COOKIES_HASH_BEFORE:0:12}) ==="

# --- 1. Iniciar Xvfb (display virtual) si no está corriendo ---
if ! pgrep -f "Xvfb $XVFB_DISPLAY" > /dev/null; then
    log "Starting Xvfb on $XVFB_DISPLAY"
    Xvfb $XVFB_DISPLAY -screen 0 1920x1080x24 -ac > /dev/null 2>&1 &
    XVFB_PID=$!
    sleep 2
    # Cleanup on exit
    trap "kill $XVFB_PID 2>/dev/null || true" EXIT
fi

export DISPLAY=$XVFB_DISPLAY

# --- 2. Iniciar Chrome con remote debugging si no está ---
if ! pgrep -f "chrome.*remote-debugging-port=$CHROME_REMOTE_PORT" > /dev/null; then
    log "Starting Chrome headless (profile: $CHROME_PROFILE)"
    google-chrome \
        --headless=new \
        --disable-gpu \
        --no-sandbox \
        --user-data-dir="$CHROME_PROFILE" \
        --remote-debugging-port=$CHROME_REMOTE_PORT \
        --remote-allow-origins='*' \
        --user-agent="$USER_AGENT" \
        --disable-blink-features=AutomationControlled \
        --window-size=1920,1080 \
        about:blank > /dev/null 2>&1 &
    CHROME_PID=$!
    sleep 4

    # Wait for Chrome to be ready
    for i in 1 2 3 4 5 6 7 8 9 10; do
        if curl -sf http://localhost:$CHROME_REMOTE_PORT/json/version > /dev/null 2>&1; then
            log "Chrome ready (PID $CHROME_PID)"
            break
        fi
        sleep 1
    done
fi

CHROME_READY_URL="http://localhost:$CHROME_REMOTE_PORT/json/version"
if ! curl -sf "$CHROME_READY_URL" > /dev/null 2>&1; then
    log "ERROR: Chrome no responde en $CHROME_READY_URL"
    exit 1
fi

# --- 3. Usar CDP para navegar YouTube, simular actividad, exportar cookies ---

# Pequeño script Python que usa websocket + chrome devtools protocol.
# Esto evita necesitar Selenium (que requiere instalación adicional).
python3 <<PYEOF
import json
import sys
import time
import urllib.request
import websocket  # viene con yt-dlp / metube venv

DEBUG_URL = "http://localhost:$CHROME_REMOTE_PORT"
TARGETS_URL = f"{DEBUG_URL}/json"

def get_ws_url():
    """Obtiene el WebSocket Debugger URL del primer target (about:blank tab)."""
    for _ in range(10):
        try:
            with urllib.request.urlopen(TARGETS_URL, timeout=2) as r:
                targets = json.loads(r.read())
                for t in targets:
                    if t.get("type") == "page":
                        return t["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(1)
    raise RuntimeError("No Chrome targets found")

def send_cmd(ws, method, params=None, msg_id=1):
    msg = {"id": msg_id, "method": method, "params": params or {}}
    ws.send(json.dumps(msg))
    while True:
        result = json.loads(ws.recv())
        if result.get("id") == msg_id:
            return result
        # ignore events

def main():
    log = lambda m: print(f"[python] {m}", flush=True)

    try:
        ws_url = get_ws_url()
        log(f"Connecting to {ws_url[:80]}...")
        ws = websocket.create_connection(ws_url, timeout=10)
        log("Connected")

        msg_id = [1]
        def cmd(method, params=None):
            msg_id[0] += 1
            send_cmd(ws, method, params, msg_id[0])
            return msg_id[0]

        # Enable Page + Network domains
        cmd("Page.enable")
        cmd("Network.enable")

        # Navegar a YouTube
        log("Navigating to https://www.youtube.com/feed/trending ...")
        cmd("Page.navigate", {"url": "https://www.youtube.com/feed/trending"})
        time.sleep(8)  # esperar que cargue

        # Check title
        result = send_cmd(ws, "Runtime.evaluate", {"expression": "document.title"})
        title = result.get("result", {}).get("result", {}).get("value", "?")
        log(f"Page title: {title!r}")

        # Detectar CAPTCHA / verificación
        if any(s in title.lower() for s in ["before you continue", "not a robot", "verify you're not a bot", "consent"]):
            log("WARNING: YouTube showed consent/verify screen. Accepting...")
            # Aceptar consent dialog si aparece
            cmd("Runtime.evaluate", {
                "expression": """
                    (() => {
                        const btn = [...document.querySelectorAll('button')].find(b => /accept|agree|continuar/i.test(b.textContent));
                        if (btn) btn.click();
                        return btn ? 'clicked' : 'no_button';
                    })()
                """
            })
            time.sleep(3)

        # Simular scroll humano
        log("Simulating scroll...")
        cmd("Runtime.evaluate", {"expression": "window.scrollTo({top: 800, behavior: 'smooth'});"})
        time.sleep(2)
        cmd("Runtime.evaluate", {"expression": "window.scrollTo({top: 400, behavior: 'smooth'});"})
        time.sleep(2)

        # Simular click en un thumbnail (mouse hover + click)
        log("Simulating click on first thumbnail...")
        cmd("Runtime.evaluate", {
            "expression": """
                (() => {
                    const thumb = document.querySelector('a[href*="/watch"]');
                    if (thumb) {
                        thumb.scrollIntoView({behavior: 'instant', block: 'center'});
                        return {found: true, href: thumb.href};
                    }
                    return {found: false};
                })()
            """
        })
        time.sleep(1)

        # Wait a bit on the video page
        log("Waiting 10s on video page (simulating watch)...")
        time.sleep(10)

        # Check if CAPTCHA appeared AFTER navigation
        result = send_cmd(ws, "Runtime.evaluate", {"expression": "document.title"})
        title2 = result.get("result", {}).get("result", {}).get("value", "?")
        log(f"After-click title: {title2!r}")

        if "not a bot" in title2.lower() or "verify you're not a bot" in title2.lower():
            log("ERROR: YouTube showed 'not a bot' — session may need manual re-login")
            sys.exit(2)

        # --- Exportar cookies ---
        log("Exporting cookies...")
        result = send_cmd(ws, "Network.getCookies", {"urls": [
            "https://www.youtube.com",
            "https://accounts.youtube.com",
            "https://accounts.google.com",
            "https://.youtube.com",
            "https://.google.com",
        ]})

        cookies = result.get("result", {}).get("cookies", [])
        log(f"Got {len(cookies)} cookies")

        # Formato Netscape
        lines = [
            "# Netscape HTTP Cookie File",
            "# https://curl.haxx.se/rfc/cookie_spec.html",
            "# Generated by youtube-session-keepalive.sh",
            "# Auto-extracted from Chromium profile on " + time.strftime("%Y-%m-%d %H:%M:%S"),
            ""
        ]

        # Dedup por nombre (la última gana)
        seen = {}
        for c in cookies:
            domain = c["domain"]
            # Netscape usa "TRUE" para domain que empieza con "." (domain match)
            http_only = "TRUE" if c.get("httpOnly", False) else "FALSE"
            # secure: si es Secure flag
            secure = "TRUE" if c.get("secure", False) else "FALSE"
            # path
            path = c.get("path", "/")
            # expiry
            expires = int(c.get("expires", 0))
            if expires < 0:
                expires = 0
            # name, value
            name = c["name"]
            value = c["value"]
            # skip non-youtube/google (chrome web store, etc.)
            if not any(x in domain for x in [".youtube.com", ".google.com", "accounts.google.com", "accounts.youtube.com"]):
                continue
            seen[name] = (domain, http_only, path, secure, expires, value)

        for name, (domain, http_only, path, secure, expires, value) in seen.items():
            # domain incluye el "." para subdominios
            lines.append(f"{domain}\t{http_only}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

        # Backup del anterior antes de pisar
        if os.path.exists("$COOKIES_OUT"):
            backup_name = "$COOKIES_OUT.bak.$(TZ=America/Lima date +%Y%m%d_%H%M%S)"
            os.rename("$COOKIES_OUT", backup_name)
            log(f"Backup: {backup_name}")

        with open("$COOKIES_OUT", "w") as f:
            f.write("\n".join(lines) + "\n")
        log(f"Wrote {len(seen)} cookies to $COOKIES_OUT")

        ws.close()
        return 0

    except Exception as e:
        log(f"EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return 1

import os
sys.exit(main())
PYEOF

PYTHON_EXIT=$?
log "Python script exit: $PYTHON_EXIT"

# --- 4. Limpiar Chrome al final ---
if [ -n "${CHROME_PID:-}" ]; then
    log "Stopping Chrome (PID $CHROME_PID)"
    kill "$CHROME_PID" 2>/dev/null || true
fi
if [ -n "${XVFB_PID:-}" ]; then
    log "Stopping Xvfb"
    kill "$XVFB_PID" 2>/dev/null || true
fi

# --- 5. Verificar cookies nuevas ---
if [ ! -f "$COOKIES_OUT" ]; then
    log "ERROR: No se generaron cookies"
    exit 1
fi

NEW_SIZE=$(stat -c%s "$COOKIES_OUT")
log "New cookies file: $NEW_SIZE bytes"

# Comparar hash
COOKIES_HASH_AFTER=$(sha256sum "$COOKIES_OUT" | cut -d' ' -f1)
log "Hash after: ${COOKIES_HASH_AFTER:0:12}"

if [ "$COOKIES_HASH_BEFORE" = "$COOKIES_HASH_AFTER" ]; then
    log "Cookies unchanged. No MeTube restart needed."
else
    log "Cookies changed. Restarting $METUBE_SERVICE to pick up new ones..."
    systemctl restart "$METUBE_SERVICE"
    sleep 3
    if systemctl is-active "$METUBE_SERVICE" > /dev/null 2>&1; then
        log "MeTube restarted OK"
    else
        log "ERROR: MeTube failed to restart"
        exit 1
    fi
fi

log "=== Keepalive DONE ==="
