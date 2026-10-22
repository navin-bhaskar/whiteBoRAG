#include "api_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include "config.h"
#include "net.h"
#include "secrets.h"

static const uint32_t BACKOFF_MS[] = {500, 1500};  // spec §3: up to 2 retries

const char *apiResultName(ApiResult r) {
  switch (r) {
    case ApiResult::Ok:          return "ok";
    case ApiResult::ConfigError: return "config error";
    case ApiResult::Throttled:   return "throttled";
    case ApiResult::Transient:   return "transient";
  }
  return "?";
}

// One POST. Returns the HTTP status, or a negative HTTPClient error code.
static int postOnce(const char *trigger, String &body) {
  WiFiClientSecure client;
  tlsConfigure(client);
  HTTPClient http;
  http.setConnectTimeout(API_TIMEOUT_MS);
  http.setTimeout(API_TIMEOUT_MS);
  if (!http.begin(client, String(API_BASE_URL) + "/captures")) return HTTPC_ERROR_CONNECTION_REFUSED;

  http.addHeader("Content-Type", "application/json");
  http.addHeader("x-api-key", API_KEY);
  char payload[96];
  snprintf(payload, sizeof payload, "{\"device_id\":\"%s\",\"trigger\":\"%s\"}", DEVICE_ID, trigger);

  int code = http.POST(String(payload));
  if (code > 0) body = http.getString();
  http.end();
  return code;
}

static bool parseTicket(const String &body, UploadTicket &out) {
  JsonDocument doc;
  if (deserializeJson(doc, body)) return false;

  const char *id = doc["capture_id"];
  const char *key = doc["key"];
  const char *url = doc["upload_url"];
  JsonObjectConst headers = doc["headers"];
  if (!id || !key || !url || headers.isNull()) return false;
  if (headers.size() > UploadTicket::MAX_HEADERS) return false;

  out.captureId = id;
  out.key = key;
  out.uploadUrl = url;
  out.headerCount = 0;
  for (JsonPairConst h : headers) {
    const char *value = h.value();
    if (!value) return false;
    out.headerNames[out.headerCount] = h.key().c_str();
    out.headerValues[out.headerCount] = value;
    out.headerCount++;
  }
  return true;
}

ApiResult requestUploadTicket(const char *trigger, UploadTicket &out) {
  for (int attempt = 0;; attempt++) {
    String body;
    uint32_t t0 = millis();
    int code = postOnce(trigger, body);
    Serial.printf("[api] POST /captures -> %d in %lu ms\n", code, (unsigned long)(millis() - t0));

    if (code == 200) {
      if (parseTicket(body, out)) return ApiResult::Ok;
      Serial.printf("[api] unusable 200 body: %s\n", body.c_str());
      return ApiResult::Transient;
    }
    if (code > 0 && code < 500) {
      Serial.printf("[api] %s\n", body.c_str());
      return code == 429 ? ApiResult::Throttled : ApiResult::ConfigError;
    }
    if (code < 0) Serial.printf("[api] %s\n", HTTPClient::errorToString(code).c_str());
    if (attempt >= 2) return ApiResult::Transient;
    delay(BACKOFF_MS[attempt]);
  }
}
