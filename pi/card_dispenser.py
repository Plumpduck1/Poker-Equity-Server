#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time

# GPIO pins
BUTTON_PIN = 22
RELAY_PIN  = 17

# ===== TUNING PARAMETERS =====
PULSE_ON   = 0.03    # motor ON per pulse (seconds)
PULSE_OFF  = 0.25    # motor OFF between pulses
CARD_REST  = 0.6     # rest after each card
MAX_CARDS  = 52
# =============================

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)   # ACTIVE-HIGH relay

relay.off()
print("🃏 Auto card feeder ready")

def pulses_for_card(card_num: int) -> int:
    """Adaptive pulse count based on stack weight."""
    if card_num <= 10:
        return 5
    elif card_num <= 25:
        return 3
    elif card_num <= 39:
        return 2
    else:
        return 1

def feed_card(card_num: int):
    pulses = pulses_for_card(card_num)
    print(f"▶ Card {card_num}: {pulses} pulses")

    for _ in range(pulses):
        relay.on()
        time.sleep(PULSE_ON)
        relay.off()
        time.sleep(PULSE_OFF)

    time.sleep(CARD_REST)

def feed_full_stack():
    print("▶ Starting full deck feed")
    for card in range(1, MAX_CARDS + 1):
        feed_card(card)
    print("■ Deck complete")

while True:
    button.wait_for_press()
    feed_full_stack()
    button.wait_for_release()
