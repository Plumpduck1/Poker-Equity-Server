#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time

BUTTON_PIN = 22
RELAY_PIN  = 17

MAX_CARDS = 52

# Aggressive timing (FAST)
PULSE_ON_START = 0.05   # heavy stack
PULSE_ON_END   = 0.015  # light stack

PULSES_START = 5
PULSES_END   = 1

PULSE_OFF = 0.06        # short settle between pulses

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)   # active-HIGH

relay.off()
print("🃏 Fast auto-feed ready")

def lerp(a, b, t):
    return a + (b - a) * t

def feed_card(card_num):
    t = card_num / MAX_CARDS

    pulse_on = lerp(PULSE_ON_START, PULSE_ON_END, t)
    pulses   = round(lerp(PULSES_START, PULSES_END, t))

    for _ in range(pulses):
        relay.on()
        time.sleep(pulse_on)
        relay.off()
        time.sleep(PULSE_OFF)

def feed_full_stack():
    start = time.time()
    for card in range(1, MAX_CARDS + 1):
        feed_card(card)
    print(f"■ Done in {time.time() - start:.2f}s")

while True:
    button.wait_for_press()
    feed_full_stack()
    button.wait_for_release()
