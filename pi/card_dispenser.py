#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice
from smartcard.System import readers
from smartcard.Exceptions import NoCardException, CardConnectionException

# ========== GPIO ==========
RELAY_PIN  = 17
BUTTON_PIN = 22

relay  = DigitalOutputDevice(RELAY_PIN)
button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)
relay.off()

# ========== NFC ==========
rlist = readers()
if not rlist:
    raise RuntimeError("No PC/SC readers found")

reader = rlist[0]
connection = reader.createConnection()

# ========== TIMING ==========
MOTOR_ON_TIME   = 0.60
REST_TIME       = 0.50
SUCCESS_REST    = 0.50
SCAN_WINDOW     = 0.80
POLL_DELAY      = 0.02
# ==========================

running = False
last_button = False
last_uid = None

print("🃏 Simple motor + RFID loop ready")

# --------------------------

def poll_button():
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

def scan_for_uid(ignore_uid):
    start = time.time()
    while time.time() - start < SCAN_WINDOW:
        poll_button()
        if not running:
            return None

        if connect_card():
            uid = read_uid()
            if uid and uid != ignore_uid:
                return uid

        time.sleep(POLL_DELAY)
    return None

# ========== MAIN LOOP ==========

while True:
    poll_button()

    if not running:
        time.sleep(0.05)
        continue

    # ---- MOTOR ON ----
    relay.on()
    start = time.time()
    while time.time() - start < MOTOR_ON_TIME:
        poll_button()
        if not running:
            relay.off()
            break
        time.sleep(0.005)
    relay.off()

    if not running:
        continue

    # ---- REST + SCAN ----
    uid = scan_for_uid(last_uid)

    if uid:
        print(f"✅ UID = {uid}")
        last_uid = uid

        # extra rest on success
        rest_start = time.time()
        while time.time() - rest_start < SUCCESS_REST:
            poll_button()
            if not running:
                break
            time.sleep(0.02)
    else:
        # normal rest
        rest_start = time.time()
        while time.time() - rest_start < REST_TIME:
            poll_button()
            if not running:
                break
            time.sleep(0.02)
