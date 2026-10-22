# WhiteBorag capture firmware

This firmware runs on the AI-Thinker ESP32-CAM. When you wave a hand in front of the IR sensor, or send `snap` over serial, the camera takes a 1600x1200 JPEG with the flash and uploads it to S3. To upload, it first asks the capture API for a pre-signed URL. The result is shown on the flash LED. The camera also always serves a live view, so you can aim it at the board.

## Wiring

| IR sensor (FC-51) | ESP32-CAM |
|-------------------|-----------|
| OUT               | IO14      |
| VCC               | 3.3V      |
| GND               | GND       |

Power the board from a solid 5 V supply that can deliver at least 1 A. With a weak supply, the board resets (brownout) when Wi-Fi transmits.

## Setup

1. **Deploy the API** in `infra/` first. The firmware needs its URL and a device API key.
2. **Generate `whiteborag_cam/secrets.h`.** This file is git-ignored and holds the Wi-Fi credentials, the API URL and the API key:
   ```
   python ESP32-cam/firmware/tools/gen_secrets.py --wifi-from <header with WIFI_SSID / WIFI_PASSWORD defines>
   ```
   Instead of `--wifi-from`, you can set the `WIFI_SSID` and `WIFI_PASSWORD` environment variables. Or copy `secrets.example.h` to `secrets.h` and fill it in by hand.
3. **Check `DEVICE_ID`** in `whiteborag_cam/config.h`. It must be one of the devices in the infra variable `devices`.
4. `certs.h` (the Amazon root CAs used for TLS) is checked in. Regenerate it with `python ESP32-cam/firmware/tools/gen_certs.py` only if the roots change.

## Build and flash

Use the arduino-cli bundled with the Arduino IDE (`<IDE>/resources/app/lib/backend/resources/arduino-cli.exe`). Board: **AI Thinker ESP32-CAM** (`esp32:esp32:esp32cam`). Run these from `whiteborag_cam/`:

```
arduino-cli compile --fqbn esp32:esp32:esp32cam --output-dir build .
arduino-cli upload  --fqbn esp32:esp32:esp32cam -p COMx --input-dir build .
```

Auto-reset doesn't work on this board, so put it into flash mode by hand:

1. Connect **IO0 to GND**, then power-cycle the board or press RST. The board only enters flash mode if IO0 is LOW at the moment it starts.
2. Run the upload.
3. **Remove the IO0 jumper** and power-cycle again to run the firmware.

If an upload fails partway, the board needs another power-cycle into flash mode before you retry.

## Serial commands

The serial port runs at 115200 baud, and commands end with a newline. `tools/serial_cmd.py` sends one command without resetting the board:

```
uv run ESP32-cam/firmware/tools/serial_cmd.py COM8 status --seconds 5
uv run ESP32-cam/firmware/tools/serial_cmd.py COM8 --seconds 60   # listen only
```

| Command                  | Action |
|--------------------------|--------|
| `snap`                   | Capture and upload, same as an IR wave |
| `status`                 | Wi-Fi, IP, memory, flash setting, IR state, last result |
| `irscan`                 | Sample the IR pin for 5 s and report how long its LOW runs are (for checking for a false "hand" at idle) |
| `flash on` / `flash off` | Use the flash for captures (default on) |
| `signals`                | Play every LED signal once |

Only one program can open the serial port at a time. Close the Arduino IDE Serial Monitor before using `serial_cmd.py`.

## LED signals

The flash LED fires at full brightness only for a capture. Everything else shows at low brightness.

| Pattern            | Meaning |
|--------------------|---------|
| 1 short pulse      | Trigger accepted |
| 2 short blinks     | Uploaded |
| 3 slow blinks      | Temporary failure (Wi-Fi, server error, rate limit); try again |
| 6 fast blinks      | Configuration error (bad API key or device, upload rejected) |

After every capture attempt, triggers are ignored for 5 s (`COOLDOWN_MS`).

## Live view

The camera always serves an 800x600 view with the flash off, at:

- `http://whiteborag-cam.local/`, which works in Windows 10+, macOS and iOS browsers
- `http://<board IP>/`, where the IP is shown by `status`. Use this on Android, which doesn't support `.local` names.

Use it to line the camera up with the board. The view pauses for about a second during each capture. Only one viewer can watch at a time. If a second browser can't connect, close the first one. The stream runs at about 2 fps, limited by the Wi-Fi signal.

**There is no password.** Anyone on the same Wi-Fi can watch the camera.

## Known issues

- **IR sensor false "hand":** the FC-51 is marginal at 3.3 V. On some setups its output sits LOW (meaning "hand") with nothing in front of it. Loose jumper wires made this much worse, and a breadboard helped. The firmware fires only when a hand *arrives*, so a sensor stuck on "hand" triggers at most once rather than repeatedly. Use `irscan` with nothing in front of the sensor: any LOW run of 20 ms or more means it is misbehaving. The lasting fix is hardware. Either power the sensor from 5 V with a voltage divider on OUT (for example 10k from OUT to IO14 and 20k from IO14 to GND), or use a sensor rated for 3.3 V.
- **Stale build cache:** arduino-cli keeps a copy of the sketch in `%LOCALAPPDATA%\arduino\sketches\<hash>\sketch\`. If you delete a source file, it can stay in that copy and still be compiled. Delete it there too.
