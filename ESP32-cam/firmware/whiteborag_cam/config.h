#pragma once

// Non-secret settings. Wi-Fi credentials and the API URL/key live in secrets.h.

#define DEVICE_ID "wb-cam-01"  // must be one of the devices in infra var.devices

// IR proximity sensor (FC-51 type), active LOW. At 3.3 V its output chatters
// at idle (LOW runs of 5-10 ms); a hand holds it LOW continuously.
#define IR_PIN            14
#define IR_MIN_LOW_MS     20    // continuous LOW this long = a hand (idle chatter never is)
#define IR_REARM_MS       200   // hand must be gone this long before the next wave counts
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
#define API_TIMEOUT_MS          10000
#define UPLOAD_TIMEOUT_MS       30000
