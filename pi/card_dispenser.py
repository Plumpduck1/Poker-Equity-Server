#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice

# =========================
# CONFIG
# =========================

BUTTON_PIN = 22        # physical pin 15
RELAY_PIN  = 17        # physical pin 11 (relay IN)

PULSE_ON  = 0.045
PULSE_OFF = 0.065
RUN_DURATION = 5.7

# =========================
# SETUP
# =========================

print("🃏 Card Dispenser Ready")

button = Button(
    BUTTON_PIN,
    pull_up=True,
    bounce_time=0.1
)

# Active-LOW relay:
#   GPIO LOW  = relay ON
#   GPIO HIGH = relay OFF
relay = DigitalOutputDevice(
    RELAY_PIN,
    active_high=False,
    initial_value=True   # drive GPIO HIGH immediately → relay OFF
)

# extra safety
relay.off()

# =========================
# LOGIC
# =========================

def dispense_cards():
    print("▶ Dispensing")
    start = time.time()

    while time.time() - start < RUN_DURATION:
        relay.on()                 # GPIO LOW → relay ON
        time.sleep(PULSE_ON)
        relay.off()                # GPIO HIGH → relay OFF
        time.sleep(PULSE_OFF)

    relay.off()
    print("■ Dispense finished")

def wait_for_button_and_dispense():
    print("⏸ Waiting for dealer button")
    button.wait_for_press()
    dispense_cards()
    button.wait_for_release()
    time.sleep(0.3)   # debounce / lockout

# =========================
# MAIN
# =========================

if __name__ == "__main__":
    try:
        while True:
            wait_for_button_and_dispense()
    except KeyboardInterrupt:
        relay.off()
        print("🛑 Shutdown")
