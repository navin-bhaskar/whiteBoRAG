#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

enum class PostResult {
  Ok,
  ConfigError,  // 400/403: a bad device key or body; never retried
  Transient,    // 5xx or a network failure, after one retry
};

const char *postResultName(PostResult r);

// POST the JPEG to SERVER_URL/captures on the laptop. On success keyOut is the capture key the server chose.
PostResult postCapture(const char *trigger, const uint8_t *data, size_t len, String &keyOut);
