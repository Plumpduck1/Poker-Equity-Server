import sys
import time
import sqlite3
import select
from smartcard.System import readers

# =============================
# CONFIG
# =============================

DB_PATH = "cards.db"

# MUST match app.py exactly
RANKS = "23456789TJQKA"
SUITS = "cdhs"
CARD_ORDER = [r + s for r in RANKS for s in SUITS]

# =============================
# UTIL
# =============================

def key_pressed():
    return select.select([sys.stdin], [], [], 0)[0]

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS card_map (
            uid TEXT PRIMARY KEY,
            card TEXT NOT NULL
        )
    """)
    db.commit()
    db.close()

def uid_exists(uid):
    db = get_db()
    cur = db.execute("SELECT card FROM card_map WHERE uid=?", (uid,))
    row = cur.fetchone()
    db.close()
    return row

def save_mapping(uid, card):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO card_map (uid, card) VALUES (?, ?)",
        (uid, card)
    )
    db.commit()
    db.close()

def count_mapped():
    db = get_db()
    cur = db.execute("SELECT COUNT(*) FROM card_map")
    count = cur.fetchone()[0]
    db.close()
    return count

# =============================
# RFID
# =============================

def get_reader():
    r = readers()
    if not r:
        print("❌ No NFC readers found")
        sys.exit(1)
    print(f"✅ Using reader: {r[0]}")
    return r[0]

def wait_for_uid(reader):
    connection = reader.createConnection()
    print("   Tap card  |  [S] skip  |  [Q] quit")

    while True:
        # Keyboard input
        if key_pressed():
            key = sys.stdin.read(1).lower()
            if key == "s":
                return None
            if key == "q":
                print("\n🛑 Training aborted safely")
                sys.exit(0)

        # RFID read
        try:
            connection.connect()
            data, sw1, sw2 = connection.transmit(
                [0xFF, 0xCA, 0x00, 0x00, 0x00]
            )
            uid = "".join(f"{b:02X}" for b in data)
            return uid
        except:
            time.sleep(0.1)

# =============================
# MAIN TRAINING LOOP
# =============================

def main():
    print("\n🃏 Poker Card Training Mode")
    print("──────────────────────────")

    init_db()
    reader = get_reader()

    already_done = count_mapped()
    if already_done > 0:
        print(f"🔁 Resuming training at card {already_done + 1}/52")

    for idx, card in enumerate(CARD_ORDER[already_done:], start=already_done + 1):
        print(f"\n[{idx:02d}/52] Present card: {card}")

        uid = wait_for_uid(reader)

        if uid is None:
            print("⏭️  Skipped")
            continue

        existing = uid_exists(uid)
        if existing:
            print(f"⚠️  UID already mapped to {existing[0]} — ignoring")
            continue

        save_mapping(uid, card)
        print(f"✅ Mapped UID {uid} → {card}")

        time.sleep(0.5)  # debounce

    # =============================
    # FINAL CHECK
    # =============================

    total = count_mapped()
    print("\n──────────────────────────")
    if total == 52:
        print("🎉 Training complete — all 52 cards mapped")
    else:
        print(f"⚠️ Training incomplete — {total}/52 cards mapped")

    print("📦 Database saved to:", DB_PATH)

if __name__ == "__main__":
    main()
