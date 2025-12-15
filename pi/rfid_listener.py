#!/usr/bin/env python3
import time
import sqlite3
import requests
from smartcard.System import readers
from smartcard.Exceptions import NoCardException

# ======================
# CONFIG
# ======================

DB_PATH = "cards.db"

SERVER_URL = "https://xavierpoker.up.railway.app/rfid"  # later
TABLE_ID = "xavierpokertable"

SEND_TO_SERVER = False    # flip True when ready
DEBOUNCE_SECONDS = 1.0

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

# ======================
# DB
# ======================

def lookup_card(uid):
    db = sqlite3.connect(DB_PATH)
    cur = db.execute("SELECT card FROM card_map WHERE uid=?", (uid,))
    row = cur.fetchone()
    db.close()
    return row[0] if row else None

# ======================
# SETUP
# ======================

print("🟢 Starting RFID listener")

r = readers()
if not r:
    raise RuntimeError("❌ No NFC reader found")

reader = r[0]
print(f"✅ Using reader: {reader}")

last_uid = None
last_time = 0

# ======================
# MAIN LOOP
# ======================

while True:
    try:
        connection = reader.createConnection()
        connection.connect()

        data, sw1, sw2 = connection.transmit(GET_UID)
        uid = "".join(f"{b:02X}" for b in data)
        now = time.time()

        # debounce
        if uid == last_uid and (now - last_time) < DEBOUNCE_SECONDS:
            time.sleep(0.1)
            continue

        last_uid = uid
        last_time = now

        card = lookup_card(uid)
        if not card:
            print(f"⚠️  Unknown UID {uid} — not trained")
            time.sleep(0.5)
            continue

        print(f"[SCAN] {uid} → {card}")

        if SEND_TO_SERVER:
            try:
                requests.post(
                    SERVER_URL,
                    timeout=2,
                    json={
                        "table_id": TABLE_ID,
                        "card": card,
                    }
                )
            except Exception as e:
                print("❌ Server send failed:", e)

        time.sleep(0.5)  # wait for removal

    except NoCardException:
        time.sleep(0.1)

    except Exception as e:
        print("❌ Reader error:", e)
        time.sleep(1)
