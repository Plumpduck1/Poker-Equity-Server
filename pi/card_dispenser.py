#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException

# ================= GPIO =================
RELAY_PIN  = 17    # Active-HIGH relay (LED on = motor on)
BUTTON_PIN = 22

relay  = DigitalOutputDevice(RELAY_PIN)
button = Button(BUTTON_PIN, pull_up=True)
relay.off()

# ================= NFC =================
rlist = readers()
if not rlist:
    raise RuntimeError("No PC/SC readers found (is pcscd running?)")

pcsc_reader = rlist[0]
connection = pcsc_reader.createConnection()

# ================= FEED CONFIG =================
MAX_CARDS = 52

# Base motor pulse (keep pulses short for separation)
BASE_ON   = 0.045   # seconds (gentle)
BASE_OFF  = 0.18    # seconds settle

# Escalation stages if no UID detected (jam recovery)
# (pulses, ON_time, OFF_time)
STAGES = [
    (3, 0.045, 0.18),   # gentle
    (5, 0.055, 0.20),   # more energy
    (7, 0.065, 0.22),   # stronger
]

# RFID polling behaviour
SCAN_WINDOW     = 0.55   # seconds to look for a NEW UID after each nudge batch
POLL_DELAY      = 0.01   # ~100 Hz polling
CLEAR_TIME      = 0.35   # must be "quiet" this long to consider cleared

# Double-feed detection
DOUBLEFEED_WINDOW   = 0.25  # after first UID, watch for another UID
# ================================================

print("🃏 ACR122U + motor feeder (jam + double-feed handling) ready")

# ------------------------------------------------

def connect_card():
    """True if we can connect to a card right now."""
    try:
        connection.connect()
        return True
    except (NoCardException, CardConnectionException):
        return False

def read_uid():
    """Read UID if a card is present, else None."""
    try:
        data, sw1, sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
        if sw1 == 0x90:
            return ''.join(f"{b:02X}" for b in data)
    except (NoCardException, CardConnectionException):
        pass
    return None

def pulse_motor(on_s: float, off_s: float):
    relay.on()
    time.sleep(on_s)
    relay.off()
    time.sleep(off_s)

def wait_for_new_uid(ignore: set, timeout: float):
    """Poll until we see a UID not in ignore, or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        if connect_card():
            uid = read_uid()
            if uid and uid not in ignore:
                return uid
        time.sleep(POLL_DELAY)
    return None

def wait_until_clear():
    """Wait until no UID has been seen for CLEAR_TIME."""
    last_seen = time.time()
    while True:
        if connect_card():
            uid = read_uid()
            if uid:
                last_seen = time.time()
        if time.time() - last_seen >= CLEAR_TIME:
            return
        time.sleep(POLL_DELAY)

def check_doublefeed(first_uid: str, ignore: set):
    """
    After getting first_uid, watch briefly for a *different* UID.
    Returns second UID if detected, else None.
    """
    start = time.time()
    while time.time() - start < DOUBLEFEED_WINDOW:
        if connect_card():
            uid = read_uid()
            if uid and uid != first_uid and uid not in ignore:
                return uid
        time.sleep(POLL_DELAY)
    return None

def feed_one_card(card_num: int, seen: set, prev_uid: str | None):
    """
    Returns uid string on success.
    Raises RuntimeError on jam or doublefeed.
    """
    ignore = set(seen)
    if prev_uid:
        ignore.add(prev_uid)

    # Try stages: gentle -> stronger
    for (pulses, on_s, off_s) in STAGES:
        # Apply a batch of nudges
        for _ in range(pulses):
            pulse_motor(on_s, off_s)

        # After the batch, aggressively scan for a NEW card UID
        uid = wait_for_new_uid(ignore=ignore, timeout=SCAN_WINDOW)
        if uid:
            # Double-feed detection: did we accidentally grab two?
            second = check_doublefeed(first_uid=uid, ignore=ignore | {uid})
            if second:
                # Stop and force a clear so we don't corrupt mapping
                relay.off()
                wait_until_clear()
                raise RuntimeError(f"DOUBLE_FEED: saw {uid} then {second}")

            # Ensure card clears before next move
            wait_until_clear()
            return uid

    # If we get here: no UID ever appeared => likely jam / stalled card / missed scan
    relay.off()
    raise RuntimeError("JAM_OR_MISSED_SCAN: no new UID detected after escalation")

def feed_and_scan_deck():
    seen = set()
    prev_uid = None
    start = time.time()

    for card_num in range(1, MAX_CARDS + 1):
        print(f"\n▶ Card {card_num}")

        try:
            uid = feed_one_card(card_num, seen=seen, prev_uid=prev_uid)
        except RuntimeError as e:
            print(f"❌ {e}")
            print("Stopping run to avoid corrupt mapping.")
            return

        print(f"✅ UID = {uid}")
        seen.add(uid)
        prev_uid = uid

    print(f"\n■ DONE in {time.time() - start:.2f}s")

# ================= MAIN LOOP =================

while True:
    print("\n⏸ Waiting for button")
    button.wait_for_press()
    print("▶ START")
    feed_and_scan_deck()
    button.wait_for_release()
