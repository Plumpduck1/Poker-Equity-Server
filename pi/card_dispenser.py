#!/usr/bin/env python3
import time
from gpiozero import Button, DigitalOutputDevice

BUTTON_PIN = 22   # physical pin 15
RELAY_PIN  = 17   # physical pin 11

RUN_DURATION = 3.0   # seconds

print("🃏 Ready")

button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.1)

# Active-LOW relay module (low-level trigger)
relay = DigitalOutputDevice(RELAY_PIN, active_high=False)

# Force OFF immediately once Python starts
relay.off()
time.sleep(0.2)
relay.off()

def run_motor(seconds: float):
    print(f"▶ Motor ON for {seconds}s")
    relay.on()               # active-low: ON = pulls GPIO low
    time.sleep(seconds)
    relay.off()
    print("■ Motor OFF")

while True:
    print("⏸ Waiting for button")
    button.wait_for_press()
    run_motor(RUN_DURATION)
    button.wait_for_release()
    time.sleep(0.25)  # debounce/lockout
