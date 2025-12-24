#!/usr/bin/env python3
from gpiozero import Button, DigitalOutputDevice
import time

BUTTON_PIN = 22
RELAY_PIN  = 17

PULSE_ON  = 0.05    # seconds motor ON (short)
REST_TIME = 0.6     # seconds motor OFF (long)

button = Button(BUTTON_PIN, pull_up=True)
relay  = DigitalOutputDevice(RELAY_PIN)   # active-HIGH

relay.off()
print("🃏 Single-card feeder ready")

def feed_one_card():
    print("▶ Feed 1 card")
    relay.on()                 # motor ON
    time.sleep(PULSE_ON)
    relay.off()                # motor OFF
    time.sleep(REST_TIME)      # let card settle
    print("■ Done")

while True:
    button.wait_for_press()
    feed_one_card()
    button.wait_for_release()  # must release to feed again
