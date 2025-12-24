#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException

# ================= GPIO =================
RELAY_PIN  = 17    # Active-HIGH relay
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

# ================= FEED CONFIG =================
MAX_CARDS = 52

# Motor timing (tuned for reliability)
PULSE_ON  = 0.04      # motor ON (seconds)
PULSE_OFF = 0.15      # settle time between nudges

# RFID timing
SCAN_TIMEOUT = 0.6    # seconds to wait for UID after a nudge
CLEAR_TIME   = 0.35   # no-card time before next card

POLL_DELAY = 0.01     # fast polling (~100 Hz)

MIN_PULSES_PER_CARD = 3
MAX_PULSES_PER_CARD = 8

# ================================================

print("🃏 Card dispenser (motor + ACR122U) ready")

# ------------------------------------------------

def connect_card():
    """Attempt to connect if a card is present."""
    try:
        connection.connect()
        return True
    except (NoCardException, CardConnectionException):
        return False

def read_uid():
    """Read UID if card is connected."""
    try:
        data, sw1, sw2 = connection.transmit(
            [0xFF, 0xCA, 0x00, 0x00, 0x00]  # GET UID
        )
        if sw1 == 0x90:
            return ''.join(f"{b:02X}" for b in data)
    except (NoCardException, CardConnectionException):
        pass
    return None

def pulse_motor():
    relay.on()
    time.sleep(PULSE_ON)
    relay.off()
    time.sleep(PULSE_OFF)

def wait_for_new_uid(ignore, timeout):
    """Poll aggressively for a NEW UID."""
    start = time.time()
    while time.time() - start < timeout:
        if connect_card():
            uid = read_uid()
            if uid and uid not in ignore:
                return uid
        time.sleep(POLL_DELAY)
    return None

def wait_until_clear():
    """Wait until no card has been seen for CLEAR_TIME."""
    last_seen = time.time()
    while True:
        if connect_card():
            uid = read_uid()
            if uid:
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
        pulses = 0

        while not uid and pulses < MAX_PULSES_PER_CARD:
            pulse_motor()
            pulses += 1

            uid = wait_for_new_uid(
                ignore=seen | ({prev_uid} if prev_uid else set()),
                timeout=SCAN_TIMEOUT
            )

        # If still no UID, keep nudging gently
        while not uid:
            pulse_motor()
            uid = wait_for_new_uid(
                ignore=seen | ({prev_uid} if prev_uid else set()),
                timeout=SCAN_TIMEOUT
            )


            print(f"✅ UID = {uid}")
            seen.add(uid)
            prev_uid = uid

        # Ensure card fully clears before next eject
        wait_until_clear()

    print(f"\n■ DONE in {time.time() - start_time:.2f}s")

# ================= MAIN LOOP =================

while True:
    print("\n⏸ Waiting for button")
    button.wait_for_press()
    print("▶ START")
    feed_and_scan_deck()
    button.wait_for_release()
