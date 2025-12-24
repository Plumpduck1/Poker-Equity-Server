#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time
import math

# GPIO pins
BUTTON_PIN = 22
RELAY_PIN  = 17

# ===== FEED CONFIG =====
MAX_CARDS = 52

# Pulse timing range (seconds)
PULSE_ON_START = 0.08   # heavy stack
PULSE_ON_END   = 0.02   # light stack

# Pulse count range
PULSES_START = 6        # heavy stack
PULSES_END   = 1        # light stack

PULSE_OFF = 0.25        # OFF time between pulses
CARD_REST = 0.7         # rest between cards
# =======================

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)   # ACTIVE-HIGH

relay.off()
print("🃏 Adaptive full-deck feeder ready")

def lerp(a, b, t):
    """Linear interpolation."""
    return a + (b - a) * t

def feed_card(card_num: int):
    # Normalize 0 → 1
    t = card_num / MAX_CARDS

    # Compute adaptive parameters
    pulse_on = lerp(PULSE_ON_START, PULSE_ON_END, t)
    pulses   = round(lerp(PULSES_START, PULSES_END, t))

    print(f"▶ Card {card_num}: {pulses} pulses @ {pulse_on:.3f}s")

    for _ in range(pulses):
        relay.on()
        time.sleep(pulse_on)
        relay.off()
        time.sleep(PULSE_OFF)

    time.sleep(CARD_REST)

def feed_full_stack():
    print("▶ Starting deck feed")
    for card in range(1, MAX_CARDS + 1):
        feed_card(card)
    print("■ Deck complete")

while True:
    button.wait_for_press()
    feed_full_stack()
    button.wait_for_release()
