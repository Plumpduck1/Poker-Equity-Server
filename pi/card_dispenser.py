#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time

BUTTON_PIN = 22
RELAY_PIN  = 17

MAX_CARDS = 52

# ===== PULSE PROFILE (~20s total) =====
PULSE_ON_START = 0.30   # strong shove at start (heavy stack)
PULSE_ON_END   = 0.10   # gentle shove at end (light stack)

PULSE_OFF = 0.08        # settle time between cards
# =====================================

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)   # ACTIVE-HIGH relay

relay.off()
print("🃏 52-pulse (~20s) adaptive feeder ready")

def lerp(a, b, t):
    return a + (b - a) * t

def feed_full_stack():
    start = time.time()

    for card in range(1, MAX_CARDS + 1):
        t = card / MAX_CARDS
        pulse_on = lerp(PULSE_ON_START, PULSE_ON_END, t)

        print(f"▶ Card {card}: ON {pulse_on:.3f}s")

        relay.on()
        time.sleep(pulse_on)
        relay.off()
        time.sleep(PULSE_OFF)

    print(f"■ Done in {time.time() - start:.2f}s")

while True:
    button.wait_for_press()
    feed_full_stack()
    button.wait_for_release()
