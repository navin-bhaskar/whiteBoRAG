#include "local_uploader.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFiClient.h>

#include "config.h"
#include "secrets.h"

static const uint32_t RETRY_DELAY_MS = 1000;

const char *postResultName(PostResult r) {
  switch (r) {
    case PostResult::Ok:          return "ok";
    case PostResult::ConfigError: return "config error";
    case PostResult::Transient:   return "transient";
  }
  return "?";
}

// One POST over plain HTTP on the LAN. Returns the HTTP status, or a negative HTTPClient error code.
static int postOnce(const char *trigger, const uint8_t *data, size_t len, String &body) {
  WiFiClient client;
  HTTPClient http;
  http.setConnectTimeout(POST_TIMEOUT_MS);
  http.setTimeout(POST_TIMEOUT_MS);
  if (!http.begin(client, String(SERVER_URL) + "/captures")) return HTTPC_ERROR_CONNECTION_REFUSED;

  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  http.addHeader("X-Trigger", trigger);
  int code = http.POST(const_cast<uint8_t *>(data), len);
  if (code > 0) body = http.getString();
  http.end();
  return code;
}

PostResult postCapture(const char *trigger, const uint8_t *data, size_t len, String &keyOut) {
  for (int attempt = 0;; attempt++) {
    String body;
    uint32_t t0 = millis();
    int code = postOnce(trigger, data, len, body);
    Serial.printf("[post] POST /captures (%u bytes) -> %d in %lu ms\n", (unsigned)len, code,
                  (unsigned long)(millis() - t0));

    if (code == 201) {
      JsonDocument doc;
      const char *key = deserializeJson(doc, body) ? nullptr : doc["key"].as<const char *>();
      keyOut = key ? key : "?";
      return PostResult::Ok;
    }
    if (code > 0 && code < 500) {
      Serial.printf("[post] %s\n", body.c_str());
      return PostResult::ConfigError;
    }
    if (code < 0) Serial.printf("[post] %s\n", HTTPClient::errorToString(code).c_str());
    if (attempt >= 1) return PostResult::Transient;
    delay(RETRY_DELAY_MS);
  }
}
