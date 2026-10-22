#pragma once

#include <stddef.h>
#include <stdint.h>

#include "api_client.h"

enum class UploadResult {
  Ok,
  Expired,    // S3 403 AccessDenied "Request has expired": get a fresh URL
  Rejected,   // any other 4xx, e.g. SignatureDoesNotMatch: a firmware/config bug
  Transient,  // 5xx, or a network failure after one retry
};

const char *uploadResultName(UploadResult r);
UploadResult uploadJpeg(const UploadTicket &t, const uint8_t *data, size_t len);
