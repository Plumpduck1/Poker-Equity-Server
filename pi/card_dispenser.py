#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time

# GPIO pins (BCM)
BUTTON_PIN = 22
RELAY_PIN  = 17

# ===== TUNING PARAMETERS =====
PULSE_ON  = 0.08    # motor ON time (seconds)
PULSE_OFF = 0.12    # motor OFF time (seconds)
PULSES    = 4       # pulses per card
LOCKOUT   = 0.3     # debounce / safety delay
# =============================

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)  # ACTIVE-HIGH relay

relay.off()  # motor OFF at startup

print("🃏 Card feeder ready")

def feed_one_card():
    print("▶ Feeding one card")
    for i in range(PULSES):
        relay.on()                 # motor ON
        time.sleep(PULSE_ON)

        relay.off()                # motor OFF
        time.sleep(PULSE_OFF)

    print("■ Card feed complete")

while True:
    button.wait_for_press()
    feed_one_card()
    button.wait_for_release()
    time.sleep(LOCKOUT)
