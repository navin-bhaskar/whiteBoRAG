#pragma once

// Non-secret settings. Wi-Fi credentials, the server URL and the device key live in secrets.h.

#define DEVICE_ID "cam-01"  // shown at boot; the server names the device from its key

// Capacitive touch module (TTP223 type) on the pin the IR sensor used.
// Default jumpers (A and B open): output HIGH while touched, momentary.
#define TOUCH_PIN           14
#define TOUCH_ACTIVE_HIGH   1     // 0 if jumper A is closed (output LOW while touched)
#define TOUCH_MIN_MS        30    // active this long = a touch (rejects glitches)
#define TOUCH_RELEASE_MS    200   // pad released this long before the next touch counts
#define COOLDOWN_MS       5000  // after every capture attempt, success or failure

// Flash LED (GPIO 4): full brightness for captures, dimmed for feedback.
#define FLASH_LED_PIN       4
#define FLASH_DEFAULT_ON    1
#define FLASH_PRE_MS        100  // LED on this long before frames are grabbed
#define FLASH_SETTLE_FRAMES 3    // frames discarded so exposure adapts to the flash
#define LED_USE_PWM         1    // 0 = full-brightness on/off blinks (PWM fallback)
#define LED_DIM_DUTY        12   // feedback brightness, out of 256

// Live view for aiming the camera (always on, no flash, no auth)
#define LIVEVIEW_HOSTNAME "whiteborag-cam"  // http://whiteborag-cam.local/
#define STREAM_FRAMESIZE  FRAMESIZE_SVGA    // 800x600: same 4:3 framing as UXGA captures

// Network
#define WIFI_CONNECT_TIMEOUT_MS 15000
#define WIFI_RESTART_AFTER_MS   (5UL * 60 * 1000)
#define POST_TIMEOUT_MS         30000  // the whole JPEG goes up in this one request
#define MDNS_LOOKUP_MS          2000   // finding a SERVER_URL host named <laptop>.local
