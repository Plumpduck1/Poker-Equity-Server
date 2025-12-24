from gpiozero import Button, DigitalOutputDevice
import time

BUTTON_PIN = 22
RELAY_PIN  = 17
RUN_DURATION = 3

relay = DigitalOutputDevice(RELAY_PIN)   # ACTIVE HIGH
button = Button(BUTTON_PIN, pull_up=True)

relay.off()   # relay OFF at start

print("Ready")

def run_motor():
    print("Motor ON")
    relay.on()              # HIGH → relay ON
    time.sleep(RUN_DURATION)
    relay.off()             # LOW → relay OFF
    print("Motor OFF")

while True:
    button.wait_for_press()
    run_motor()
    button.wait_for_release()
    time.sleep(0.3)
