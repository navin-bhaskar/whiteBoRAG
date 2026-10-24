#include "uploader.h"

#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include "config.h"
#include "net.h"

const char *uploadResultName(UploadResult r) {
  switch (r) {
    case UploadResult::Ok:        return "ok";
    case UploadResult::Expired:   return "expired";
    case UploadResult::Rejected:  return "rejected";
    case UploadResult::Transient: return "transient";
  }
  return "?";
}

// One PUT. Returns the HTTP status, or a negative HTTPClient error code.
static int putOnce(const UploadTicket &t, const uint8_t *data, size_t len, String &body) {
  WiFiClientSecure client;
  tlsConfigure(client);
  HTTPClient http;
  http.setConnectTimeout(API_TIMEOUT_MS);
  http.setTimeout(UPLOAD_TIMEOUT_MS);
  if (!http.begin(client, t.uploadUrl)) return HTTPC_ERROR_CONNECTION_REFUSED;

  // Exactly the returned headers: they are part of the SigV4 signature.
  for (int i = 0; i < t.headerCount; i++) http.addHeader(t.headerNames[i], t.headerValues[i]);

  int code = http.sendRequest("PUT", const_cast<uint8_t *>(data), len);
  if (code > 0 && code != 200) body = http.getString();  // S3 explains failures in XML
  http.end();
  return code;
}

UploadResult uploadJpeg(const UploadTicket &t, const uint8_t *data, size_t len) {
  for (int attempt = 0;; attempt++) {
    String body;
    uint32_t t0 = millis();
    int code = putOnce(t, data, len, body);
    Serial.printf("[s3] PUT %u bytes -> %d in %lu ms\n", (unsigned)len, code,
                  (unsigned long)(millis() - t0));

    if (code == 200) return UploadResult::Ok;
    if (code > 0) {
      Serial.println(body);
      if (code == 403 && body.indexOf("AccessDenied") >= 0 && body.indexOf("expired") >= 0) {
        return UploadResult::Expired;
      }
      return code < 500 ? UploadResult::Rejected : UploadResult::Transient;
    }
    Serial.printf("[s3] %s\n", HTTPClient::errorToString(code).c_str());
    if (attempt >= 1) return UploadResult::Transient;  // spec §4: retry a network error once
    delay(500);
  }
}
