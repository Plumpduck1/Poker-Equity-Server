#!/usr/bin/env python3
import time
from gpiozero import Button, OutputDevice

# =========================
# CONFIG
# =========================

BUTTON_PIN = 22        # physical pin 15
RELAY_PIN  = 17        # physical pin 11
RELAY_ACTIVE_HIGH = False   # active-LOW relay

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

relay = OutputDevice(
    RELAY_PIN,
    active_high=RELAY_ACTIVE_HIGH,
    initial_value=False   # relay OFF at boot
)

def dispense_cards():
    print("▶ Dispensing")
    start = time.time()

    while time.time() - start < RUN_DURATION:
        relay.on()
        time.sleep(PULSE_ON)
        relay.off()
        time.sleep(PULSE_OFF)

    relay.off()
    print("■ Dispense finished")

# =========================
# MAIN LOOP
# =========================

def wait_for_button_and_dispense():
    print("⏸ Waiting for dealer button")
    button.wait_for_press()
    dispense_cards()
    button.wait_for_release()
    time.sleep(0.3)

if __name__ == "__main__":
    try:
        while True:
            wait_for_button_and_dispense()
    except KeyboardInterrupt:
        relay.off()
        print("🛑 Shutdown")
