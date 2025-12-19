import sys
import time
import sqlite3
import select
from smartcard.System import readers

# =============================
# CONFIG
# =============================

DB_PATH = "cards.db"

RANKS = "23456789TJQKA"
SUITS = "cdhs"

# Suit-major order
CARD_ORDER = [r + s for s in SUITS for r in RANKS]

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

def reset_db():
    db = get_db()
    db.execute("DELETE FROM card_map")
    db.commit()
    db.close()

def delete_uid(uid):
    db = get_db()
    db.execute("DELETE FROM card_map WHERE uid=?", (uid,))
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

def wait_for_uid(reader, last_uid=None):
    connection = reader.createConnection()
    print("   Tap card  |  [S] skip  |  [B] back  |  [R] reset  |  [Q] quit")

    while True:
        if key_pressed():
            key = sys.stdin.read(1).lower()
            if key == "s":
                return "__SKIP__"
            if key == "b":
                return "__BACK__"
            if key == "r":
                return "__RESET__"
            if key == "q":
                print("\n🛑 Training aborted safely")
                sys.exit(0)

        try:
            connection.connect()
            data, sw1, sw2 = connection.transmit(
                [0xFF, 0xCA, 0x00, 0x00, 0x00]
            )
            uid = "".join(f"{b:02X}" for b in data)

            if uid == last_uid:
                time.sleep(0.1)
                continue

            return uid

        except:
            time.sleep(0.1)

def wait_for_removal(reader, uid):
    connection = reader.createConnection()
    print("   Remove card...")

    while True:
        try:
            connection.connect()
            data, sw1, sw2 = connection.transmit(
                [0xFF, 0xCA, 0x00, 0x00, 0x00]
            )
            current_uid = "".join(f"{b:02X}" for b in data)
            if current_uid != uid:
                return
        except:
            return
        time.sleep(0.1)

# =============================
# MAIN LOOP
# =============================

def main():
    print("\n🃏 Poker Card Training Mode")
    print("──────────────────────────")

    init_db()
    reader = get_reader()

    history = []          # [(uid, card)]
    last_uid = None
    index = count_mapped()

    if index > 0:
        print(f"🔁 Resuming training at card {index + 1}/52")

    while index < 52:
        card = CARD_ORDER[index]
        print(f"\n[{index + 1:02d}/52] Present card: {card}")

        result = wait_for_uid(reader, last_uid)

        # RESET
        if result == "__RESET__":
            print("\n🔄 Resetting training — starting from 1/52")
            reset_db()
            history.clear()
            last_uid = None
            index = 0
            continue

        # BACK
        if result == "__BACK__":
            if not history:
                print("⚠️ Already at first card")
                continue

            uid, prev_card = history.pop()
            delete_uid(uid)
            index -= 1
            last_uid = None
            print(f"↩️ Removed mapping for {prev_card}, going back")
            continue

        # SKIP
        if result == "__SKIP__":
            print("⏭️ Skipped")
            index += 1
            last_uid = None
            continue

        uid = result

        if uid_exists(uid):
            print("⚠️ UID already mapped — ignoring")
            wait_for_removal(reader, uid)
            last_uid = uid
            continue

        save_mapping(uid, card)
        history.append((uid, card))
        print(f"✅ Mapped UID {uid} → {card}")

        wait_for_removal(reader, uid)
        last_uid = uid
        index += 1

    # =============================
    # FINAL
    # =============================

    print("\n──────────────────────────")
    print("🎉 Training complete — all 52 cards mapped")
    print("📦 Database saved to:", DB_PATH)

if __name__ == "__main__":
    main()
