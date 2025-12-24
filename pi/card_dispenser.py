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

running = False

print("🃏 Card feeder ready (button = toggle run/stop)")

# ------------------------------------------------

def toggle_running():
    global running
    running = not running
    if not running:
        relay.off()
        print("⛔ STOPPED")
    else:
        print("▶ STARTED")

button.when_pressed = toggle_running

# ------------------------------------------------

def ensure_running():
    if not running:
        raise RuntimeError("Stopped")

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
        ensure_running()
        time.sleep(0.005)
    relay.off()

def dwell_and_scan(ignore, dwell_time, scan_window):
    # motor OFF
    start = time.time()
    while time.time() - start < dwell_time:
        ensure_running()
        time.sleep(0.01)

    seen = {}
    scan_start = time.time()

    while time.time() - scan_start < scan_window:
        ensure_running()

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
        ensure_running()

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
        ensure_running()

        ignore = set(seen)
        if prev_uid:
            ignore.add(prev_uid)

        uid = None
        jam_attempts = 0

        while not uid:
            ensure_running()

            # ----- NORMAL FAST ATTEMPT -----
            pulse(NORMAL_PULSE_ON)
            uid = dwell_and_scan(
                ignore,
                NORMAL_DWELL,
                NORMAL_SCAN_WIN
            )
            if uid:
                break

            # ----- JAM FIX MODE -----
            jam_attempts += 1
            print("⚠️ Jam recovery")

            for _ in range(JAM_BURST_PULSES):
                pulse(NORMAL_PULSE_ON)
                time.sleep(JAM_INTER_PULSE)

            uid = dwell_and_scan(
                ignore,
                JAM_DWELL,
                JAM_SCAN_WIN
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

# ================= MAIN LOOP =================

while True:
    try:
        if running:
            feed_and_scan_deck()
            running = False
            relay.off()
    except RuntimeError:
        relay.off()
        time.sleep(0.1)
