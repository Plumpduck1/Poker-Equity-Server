#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException

# ================= GPIO =================
RELAY_PIN  = 17
BUTTON_PIN = 22

relay  = DigitalOutputDevice(RELAY_PIN)
button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
relay.off()

# ================= NFC =================
rlist = readers()
if not rlist:
    raise RuntimeError("No PC/SC readers found")

reader = rlist[0]
connection = reader.createConnection()

# ================= CONFIG =================
MAX_CARDS = 52

# ---- NORMAL MODE (FAST) ----
NORMAL_STEP_TIME = 0.45
NORMAL_PULSE_ON  = NORMAL_STEP_TIME / 3
NORMAL_DWELL     = NORMAL_STEP_TIME * 2 / 3
NORMAL_SCAN_WIN  = 0.40

# ---- JAM MODE (SLOW & SAFE) ----
JAM_PULSE_ON     = NORMAL_PULSE_ON
JAM_DWELL        = 0.90
JAM_SCAN_WIN     = 0.80
JAM_RETRY_DELAY  = 1.00   # <-- big wait between bursts

# ---- RFID ----
STABLE_READS = 2
POLL_DELAY   = 0.01

# ---- CLEAR ----
CLEAR_TIME = 0.35
# ========================================

running = False
last_button = False

print("🃏 Card feeder ready (button = toggle)")

# ------------------------------------------------

def poll_button():
    """Edge-detect button and toggle running."""
    global running, last_button
    pressed = button.is_pressed
    if pressed and not last_button:
        running = not running
        if running:
            print("▶ STARTED")
        else:
            relay.off()
            print("⛔ STOPPED")
    last_button = pressed

def connect_card():
    try:
        connection.connect()
        return True
    except (NoCardException, CardConnectionException):
        return False

def read_uid():
    try:
        data, sw1, sw2 = connection.transmit(
            [0xFF, 0xCA, 0x00, 0x00, 0x00]
        )
        if sw1 == 0x90:
            return ''.join(f"{b:02X}" for b in data)
    except (NoCardException, CardConnectionException):
        pass
    return None

def pulse(on_time):
    relay.on()
    start = time.time()
    while time.time() - start < on_time:
        poll_button()
        if not running:
            relay.off()
            return False
        time.sleep(0.005)
    relay.off()
    return True

def dwell_and_scan(ignore, dwell_time, scan_window):
    # --- dwell (motor OFF) ---
    start = time.time()
    while time.time() - start < dwell_time:
        poll_button()
        if not running:
            return None
        time.sleep(0.01)

    # --- scan ---
    seen = {}
    scan_start = time.time()

    while time.time() - scan_start < scan_window:
        poll_button()
        if not running:
            return None

        if connect_card():
            uid = read_uid()
            if uid and uid not in ignore:
                seen[uid] = seen.get(uid, 0) + 1
                if seen[uid] >= STABLE_READS:
                    return uid

        time.sleep(POLL_DELAY)

    return None

def wait_until_clear():
    clear_start = None

    while True:
        poll_button()
        if not running:
            return False

        uid = None
        if connect_card():
            uid = read_uid()

        if uid is None:
            if clear_start is None:
                clear_start = time.time()
            elif time.time() - clear_start >= CLEAR_TIME:
                return True
        else:
            clear_start = None

        time.sleep(POLL_DELAY)

def feed_one_card(seen, prev_uid):
    ignore = set(seen)
    if prev_uid:
        ignore.add(prev_uid)

    while running:
        # ===== NORMAL FAST ATTEMPT =====
        if not pulse(NORMAL_PULSE_ON):
            return None

        uid = dwell_and_scan(ignore, NORMAL_DWELL, NORMAL_SCAN_WIN)
        if uid:
            return uid

        # ===== JAM FIX (SINGLE BURST) =====
        print("⚠️ Jam recovery")

        if not pulse(JAM_PULSE_ON):
            return None

        uid = dwell_and_scan(ignore, JAM_DWELL, JAM_SCAN_WIN)
        if uid:
            return uid

        # big pause before next attempt
        start = time.time()
        while time.time() - start < JAM_RETRY_DELAY:
            poll_button()
            if not running:
                return None
            time.sleep(0.02)

    return None

# ================= MAIN LOOP =================

seen = set()
prev_uid = None
card_num = 1

while True:
    poll_button()

    if not running:
        time.sleep(0.05)
        continue

    print(f"\n▶ Card {card_num}")
    uid = feed_one_card(seen, prev_uid)

    if not running or not uid:
        continue

    print(f"✅ UID = {uid}")
    seen.add(uid)
    prev_uid = uid
    card_num += 1

    wait_until_clear()

    if card_num > MAX_CARDS:
        print("\n■ DONE")
        running = False
        relay.off()
        seen.clear()
        prev_uid = None
        card_num = 1
