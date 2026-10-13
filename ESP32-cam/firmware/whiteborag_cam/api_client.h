#pragma once

#include <Arduino.h>

// One presigned upload slot from POST /captures (spec §3).
struct UploadTicket {
  static const int MAX_HEADERS = 4;
  String captureId;
  String key;
  String uploadUrl;  // ~1.5 KB: it carries X-Amz-Security-Token
  String headerNames[MAX_HEADERS];
  String headerValues[MAX_HEADERS];
  int headerCount = 0;
};

enum class ApiResult {
  Ok,
  ConfigError,  // 400/403 (bad request, missing or wrong key) or other 4xx; never retried
  Throttled,    // 429 usage-plan limit; never retried, the cooldown covers it
  Transient,    // 5xx/network/TLS failure after 2 retries, or an unusable 200 body
};

const char *apiResultName(ApiResult r);
ApiResult requestUploadTicket(const char *trigger, UploadTicket &out);
