#pragma once

// Non-secret settings. Wi-Fi credentials and the API URL/key live in secrets.h.

#define DEVICE_ID "wb-cam-01"  // must be one of the devices in infra var.devices

// IR proximity sensor (FC-51/TCRT5000 type): push-pull output, active LOW.
#define IR_PIN       14
#define IR_STABLE_MS 150   // must read LOW this long to count; rejects flicker
#define COOLDOWN_MS  5000  // after every capture attempt, success or failure

// Flash LED (GPIO 4): full brightness for captures, dimmed for feedback.
#define FLASH_LED_PIN       4
#define FLASH_DEFAULT_ON    1
#define FLASH_PRE_MS        100  // LED on this long before frames are grabbed
#define FLASH_SETTLE_FRAMES 3    // frames discarded so exposure adapts to the flash
#define LED_USE_PWM         1    // 0 = full-brightness on/off blinks (PWM fallback)
#define LED_DIM_DUTY        12   // feedback brightness, out of 256

// Network
#define WIFI_CONNECT_TIMEOUT_MS 15000
#define WIFI_RESTART_AFTER_MS   (5UL * 60 * 1000)
#define API_TIMEOUT_MS          10000
#define UPLOAD_TIMEOUT_MS       30000
