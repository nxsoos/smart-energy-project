# Flashing

1. Open `esp32/firmware/ESP32_code.c` in Arduino IDE or an ESP32-compatible build flow.
2. Install the libraries listed in `esp32/libraries.txt`.
3. Select the ESP32 board and serial port.
4. Flash the firmware.
5. If already configured, call `POST /reset` or clear NVS/preferences to return to setup mode.
