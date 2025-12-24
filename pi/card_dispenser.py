#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException

# ================= GPIO =================
RELAY_PIN  = 17     # active-HIGH relay
BUTTON_PIN = 22

relay  = DigitalOutputDevice(RELAY_PIN)
button = Button(BUTTON_PIN, pull_up=True)
relay.off()

# ================= NFC =================
rlist = readers()
if not rlist:
    raise RuntimeError("No PC/SC readers found")

reader = rlist[0]
connection = reader.createConnection()

# ================= CONFIG =================
MAX_CARDS = 52

# Micro-pulse motion (separation-safe)
PULSE_ON   = 0.020     # very short nudge
PULSE_OFF  = 0.045     # settle between nudges

# How many nudges before a forced dwell+scan
PULSES_PER_STEP = 3

# Reader dwell + scan
DWELL_TIME   = 0.10    # **CRITICAL**: card stationary over antenna
SCAN_WINDOW  = 0.80    # total time allowed to detect UID
CLEAR_TIME   = 0.35

POLL_DELAY = 0.01
# ========================================

print("🃏 Card feeder with guaranteed RFID dwell ready")

# ------------------------------------------------

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

def micro_step():
    """Move card slightly without letting the next card follow."""
    for _ in range(PULSES_PER_STEP):
        relay.on()
        time.sleep(PULSE_ON)
        relay.off()
        time.sleep(PULSE_OFF)

def dwell_and_scan(ignore):
    """Hold card stationary and aggressively scan."""
    relay.off()
    time.sleep(DWELL_TIME)  # <-- THIS IS THE FIX

    start = time.time()
    while time.time() - start < SCAN_WINDOW:
        if connect_card():
            uid = read_uid()
            if uid and uid not in ignore:
                return uid
        time.sleep(POLL_DELAY)
    return None

def wait_until_clear():
    last_seen = time.time()
    while True:
        if connect_card():
            if read_uid():
                last_seen = time.time()
        if time.time() - last_seen >= CLEAR_TIME:
            return
        time.sleep(POLL_DELAY)

def feed_and_scan_deck():
    seen = set()
    prev_uid = None
    start_time = time.time()

    for card_num in range(1, MAX_CARDS + 1):
        print(f"\n▶ Card {card_num}")
        uid = None

        ignore = set(seen)
        if prev_uid:
            ignore.add(prev_uid)

        # Ratchet card forward until RFID sees it
        while not uid:
            micro_step()
            uid = dwell_and_scan(ignore)

        print(f"✅ UID = {uid}")
        seen.add(uid)
        prev_uid = uid

        wait_until_clear()

    print(f"\n■ DONE in {time.time() - start_time:.1f}s")

# ================= MAIN =================

while True:
    print("\n⏸ Waiting for button")
    button.wait_for_press()
    print("▶ START")
    feed_and_scan_deck()
    button.wait_for_release()
