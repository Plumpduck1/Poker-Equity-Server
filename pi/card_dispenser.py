#!/usr/bin/env python3
import time
from gpiozero import Button, OutputDevice

# =========================
# CONFIG
# =========================

BUTTON_PIN = 17          # GPIO for button
RELAY_PIN = 27           # GPIO for relay
RELAY_ACTIVE_HIGH = True # set False if relay triggers on LOW

PULSE_ON  = 0.045
PULSE_OFF = 0.065
RUN_DURATION = 5.7


# =========================
# SETUP
# =========================

print("🃏 Card Dispenser Controller Starting")

button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.1)

relay = OutputDevice(
    RELAY_PIN,
    active_high=RELAY_ACTIVE_HIGH,
    initial_value=False
)

print("✅ Ready")
print("Press button to dispense cards")

# =========================
# DISPENSE LOGIC
# =========================

def dispense_cards():
    print("▶ Dispensing started")
    start = time.time()

    while (time.time() - start) < RUN_DURATION:
        relay.on()
        time.sleep(PULSE_ON)

        relay.off()
        time.sleep(PULSE_OFF)

    relay.off()
    print("■ Dispensing finished")

# =========================
# MAIN LOOP
# =========================

try:
    while True:
        button.wait_for_press()
        dispense_cards()

        # wait until button released to avoid retrigger
        button.wait_for_release()
        time.sleep(0.3)

except KeyboardInterrupt:
    print("\n🛑 Shutting down safely")

finally:
    relay.off()
