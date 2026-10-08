#pragma once

// Copy this file to config.h and fill in your values.
// config.h is git-ignored so credentials never get committed.

#define WIFI_SSID     "your-wifi-ssid"
#define WIFI_PASSWORD "your-wifi-password"

// Optional: a pre-signed S3 PUT URL to upload to once at boot.
// Leave empty ("") to only upload URLs pasted over the serial monitor.
// Pre-signed URLs expire, so pasting over serial is usually more convenient.
#define S3_PRESIGNED_URL ""

// Must match the ContentType the URL was signed with (if any).
#define UPLOAD_CONTENT_TYPE "image/jpeg"

// On-board flash LED (GPIO 4). Can also be toggled at runtime: "flash on|off".
#define FLASH_DEFAULT_ON    1    // 1 = flash fires on every capture
#define FLASH_PRE_MS        100  // LED on this long before frames are grabbed
#define FLASH_SETTLE_FRAMES 3    // frames discarded so exposure adapts to the flash

// TLS: by default the certificate is NOT verified (fine for bench testing).
// For real verification, define S3_ROOT_CA as the PEM string of
// "Amazon Root CA 1" (https://www.amazontrust.com/repository/AmazonRootCA1.pem):
// #define S3_ROOT_CA "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"
