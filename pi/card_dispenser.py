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

# === HUMAN RHYTHM ===
STEP_TIME = 0.60        # total pinch + rest
PULSE_ON  = STEP_TIME / 3
DWELL_OFF = STEP_TIME * 2 / 3

# RFID behaviour
SCAN_WINDOW   = 0.80
STABLE_READS  = 2
POLL_DELAY    = 0.01

# Clear detection
CLEAR_TIME    = 0.35
# ========================================

print("🃏 Pulse+dwell feeder with emergency stop ready")

# ------------------------------------------------

def stop_everything():
    relay.off()
    print("⛔ STOPPED")
    raise KeyboardInterrupt

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

def pulse_once():
    relay.on()
    start = time.time()

    while time.time() - start < PULSE_ON:
        if button.is_pressed:
            stop_everything()
        time.sleep(0.005)

    relay.off()

def dwell_and_scan(ignore):
    # motor OFF, sacred dwell
    start = time.time()
    while time.time() - start < DWELL_OFF:
        if button.is_pressed:
            stop_everything()
        time.sleep(0.01)

    seen = {}
    scan_start = time.time()

    while time.time() - scan_start < SCAN_WINDOW:
        if button.is_pressed:
            stop_everything()

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
        if button.is_pressed:
            stop_everything()

        uid = None
        if connect_card():
            uid = read_uid()

        if uid is None:
            if clear_start is None:
                clear_start = time.time()
            elif time.time() - clear_start >= CLEAR_TIME:
                return
        else:
            clear_start = None

        time.sleep(POLL_DELAY)

def feed_and_scan_deck():
    seen = set()
    prev_uid = None
    start_time = time.time()

    for card_num in range(1, MAX_CARDS + 1):
        print(f"\n▶ Card {card_num}")

        ignore = set(seen)
        if prev_uid:
            ignore.add(prev_uid)

        uid = None

        while not uid:
            pulse_once()
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
    try:
        print("▶ START")
        feed_and_scan_deck()
    except KeyboardInterrupt:
        relay.off()
    button.wait_for_release()
