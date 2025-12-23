#!/usr/bin/env python3
import RPi.GPIO as GPIO
import time

BUTTON_PIN = 22
RELAY_PIN  = 17
RUN_DURATION = 3

GPIO.setmode(GPIO.BCM)

GPIO.setup(RELAY_PIN, GPIO.OUT)
GPIO.output(RELAY_PIN, GPIO.HIGH)   # relay OFF by default

GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

print("🃏 Ready")

try:
    while True:
        if GPIO.input(BUTTON_PIN) == GPIO.LOW:
            print("▶ Motor ON")
            GPIO.output(RELAY_PIN, GPIO.LOW)   # relay ON
            time.sleep(RUN_DURATION)
            GPIO.output(RELAY_PIN, GPIO.HIGH)  # relay OFF
            print("■ Motor OFF")
            time.sleep(0.3)
finally:
    GPIO.cleanup()
