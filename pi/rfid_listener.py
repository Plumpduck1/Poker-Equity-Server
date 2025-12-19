#!/usr/bin/env python3
import time
import sqlite3
import requests
from smartcard.System import readers
from smartcard.Exceptions import NoCardException

from card_dispenser import wait_for_button_and_dispense

# ======================
# CONFIG
# ======================

DB_PATH = "cards.db"
SERVER = "https://xavierpoker.up.railway.app"
TABLE_ID = "xavierpokertable"

POLL_INTERVAL = 0.5
DEBOUNCE_SECONDS = 0.6

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
# RFID SETUP
# ======================

print("🟢 RFID listener starting")

r = readers()
if not r:
    raise RuntimeError("❌ No RFID reader")

reader = r[0]
print(f"✅ Using reader: {reader}")

# ======================
# STATE
# ======================

state = "IDLE"
ufids = []
last_uid = None
last_time = 0

# ======================
# SERVER COMM
# ======================

def get_command():
    try:
        r = requests.get(f"{SERVER}/pi/command", timeout=2)
        return r.json().get("action")
    except:
        return None

def send_deck():
    print("📤 Sending deck to server")
    requests.post(
        f"{SERVER}/pi/deck",
        json={
            "table_id": TABLE_ID,
            "ufids": ufids
        },
        timeout=5
    )

# ======================
# RFID LOOP
# ======================

def scan_loop():
    global last_uid, last_time

    while True:
        try:
            connection = reader.createConnection()
            connection.connect()

            data, _, _ = connection.transmit(GET_UID)
            uid = "".join(f"{b:02X}" for b in data)
            now = time.time()

            if uid == last_uid and (now - last_time) < DEBOUNCE_SECONDS:
                return

            last_uid = uid
            last_time = now

            if uid in ufids:
                return

            card = lookup_card(uid)
            if not card:
                print(f"⚠️ Unknown UID {uid}")
                return

            ufids.append(uid)
            print(f"[SCAN] {len(ufids)} → {uid} ({card})")

        except NoCardException:
            pass

# ======================
# MAIN LOOP
# ======================

while True:
    cmd = get_command()

    if cmd == "prepare_scan" and state == "IDLE":
        print("🟡 ARMED")
        ufids.clear()
        state = "ARMED"

    elif state == "ARMED":
        wait_for_button_and_dispense()
        state = "SCANNING"

    elif state == "SCANNING":
        scan_loop()
        if len(ufids) >= 52:
            state = "DONE"

    elif state == "DONE":
        send_deck()
        state = "IDLE"

    time.sleep(POLL_INTERVAL)
