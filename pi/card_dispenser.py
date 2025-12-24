#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time

# GPIO pins
BUTTON_PIN = 22
RELAY_PIN  = 17

# Pulse timing (short bursts)
PULSE_ON  = 0.03    # 30 ms ON
PULSE_OFF = 0.25    # 250 ms OFF between pulses
CARD_REST = 0.6     # rest after a card is fed

MAX_CARDS = 52

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)   # active-HIGH

relay.off()
cards_fed = 0

print("🃏 Adaptive card feeder ready")

def pulses_for_card(card_number: int) -> int:
    """Return number of pulses based on stack weight."""
    if card_number <= 10:
        return 5
    elif card_number <= 25:
        return 3
    elif card_number <= 39:
        return 2
    else:
        return 1

def feed_one_card():
    global cards_fed

    if cards_fed >= MAX_CARDS:
        print("Deck empty")
        return

    cards_fed += 1
    pulses = pulses_for_card(cards_fed)

    print(f"▶ Card {cards_fed}: {pulses} pulses")

    for _ in range(pulses):
        relay.on()
        time.sleep(PULSE_ON)

        relay.off()
        time.sleep(PULSE_OFF)

    time.sleep(CARD_REST)
    print("■ Donee")

while True:
    button.wait_for_press()
    feed_one_card()
    button.wait_for_release()
