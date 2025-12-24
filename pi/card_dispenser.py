#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice
from smartcard.System import readers
from smartcard.Exceptions import CardConnectionException

# ================= GPIO =================
RELAY_PIN  = 17    # active-HIGH relay
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

# ================= FEED SETTINGS =================
MAX_CARDS = 52

PULSE_ON  = 0.04     # motor ON (seconds)
PULSE_OFF = 0.15     # settle time

SCAN_TIMEOUT = 0.4   # seconds to wait for UID
CLEAR_TIME   = 0.35  # no-card time before next eject
# ================================================

print("🃏 ACR122U + motor feeder ready")

def connect_card():
    try:
        connection.connect()
        return True
    except CardConnectionException:
        return False

def read_uid():
    """Return UID string if card present, else None."""
    try:
        data, sw1, sw2 = connection.transmit(
            [0xFF, 0xCA, 0x00, 0x00, 0x00]  # GET UID
        )
        if sw1 == 0x90:
            return ''.join(f"{x:02X}" for x in data)
    except CardConnectionException:
        pass
    return None

def pulse_motor():
    relay.on()
    time.sleep(PULSE_ON)
    relay.off()
    time.sleep(PULSE_OFF)

def wait_for_new_uid(ignore, timeout):
    start = time.time()
    while time.time() - start < timeout:
        if connect_card():
            uid = read_uid()
            if uid and uid not in ignore:
                return uid
        time.sleep(0.01)  # fast polling
    return None

def wait_until_clear():
    last_seen = time.time()
    while True:
        if connect_card():
            uid = read_uid()
            if uid:
                last_seen = time.time()
        if time.time() - last_seen >= CLEAR_TIME:
            return
        time.sleep(0.01)

def feed_and_scan_deck():
    seen = set()
    prev_uid = None

    for card_num in range(1, MAX_CARDS + 1):
        print(f"\n▶ Card {card_num}")

        uid = None
        while not uid:
            pulse_motor()
            uid = wait_for_new_uid(
                ignore=seen | ({prev_uid} if prev_uid else set()),
                timeout=SCAN_TIMEOUT
            )

        print(f"✅ UID = {uid}")
        seen.add(uid)
        prev_uid = uid

        wait_until_clear()

    print("\n■ Deck complete")

# ================= MAIN LOOP =================

while True:
    print("\n⏸ Waiting for button")
    button.wait_for_press()
    print("▶ START")
    feed_and_scan_deck()
    button.wait_for_release()
