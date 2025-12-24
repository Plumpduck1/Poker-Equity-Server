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

# ---- NORMAL (FAST) MODE ----
NORMAL_STEP_TIME = 0.45
NORMAL_PULSE_ON  = NORMAL_STEP_TIME / 3
NORMAL_DWELL     = NORMAL_STEP_TIME * 2 / 3
NORMAL_SCAN_WIN  = 0.40

# ---- JAM FIX MODE ----
JAM_BURST_PULSES = 2
JAM_INTER_PULSE  = 0.05
JAM_DWELL        = 0.90
JAM_SCAN_WIN     = 0.80
MAX_JAM_ATTEMPTS = 3

# ---- RFID ----
STABLE_READS = 2
POLL_DELAY   = 0.01

# ---- CLEAR DETECTION ----
CLEAR_TIME = 0.35
# ========================================

print("🃏 Card feeder (fast + jam-safe) ready")

# ------------------------------------------------

def emergency_stop():
    relay.off()
    print("⛔ EMERGENCY STOP")
    raise KeyboardInterrupt

def check_button():
    if button.is_pressed:
        emergency_stop()

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
        check_button()
        time.sleep(0.005)
    relay.off()

def dwell_and_scan(ignore, dwell_time, scan_window):
    # motor must be OFF here
    start = time.time()
    while time.time() - start < dwell_time:
        check_button()
        time.sleep(0.01)

    seen = {}
    scan_start = time.time()

    while time.time() - scan_start < scan_window:
        check_button()

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
        check_button()

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
        jam_attempts = 0

        while not uid:
            # ===== FAST NORMAL ATTEMPT =====
            pulse(NORMAL_PULSE_ON)
            uid = dwell_and_scan(
                ignore,
                dwell_time=NORMAL_DWELL,
                scan_window=NORMAL_SCAN_WIN
            )
            if uid:
                break

            # ===== JAM FIX MODE =====
            jam_attempts += 1
            print("⚠️ Jam recovery")

            for _ in range(JAM_BURST_PULSES):
                pulse(NORMAL_PULSE_ON)
                time.sleep(JAM_INTER_PULSE)

            uid = dwell_and_scan(
                ignore,
                dwell_time=JAM_DWELL,
                scan_window=JAM_SCAN_WIN
            )

            if jam_attempts >= MAX_JAM_ATTEMPTS and not uid:
                print("⛔ Persistent jam — backing off")
                time.sleep(1.0)
                jam_attempts = 0

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
