#pragma once

// Template for secrets.h (git-ignored). Generate the real file with:
//   python ESP32-cam/firmware/tools/gen_secrets.py --wifi-from <header with WIFI_* defines>
// or copy this file to secrets.h and fill it in from `terraform -chdir=infra output`.

#define WIFI_SSID     "your-wifi-ssid"
#define WIFI_PASSWORD "your-wifi-password"
#define API_BASE_URL  "https://xxxxxxxxxx.execute-api.ap-south-1.amazonaws.com/v1"  // no trailing slash
#define API_KEY       "device-api-key-value"
