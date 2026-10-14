#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_camera.h"

// A JPEG copied out of the camera, so the camera is free again while it
// uploads. Frees itself.
struct CapturedJpeg {
  uint8_t *buf = nullptr;
  size_t len = 0;
  CapturedJpeg() = default;
  CapturedJpeg(const CapturedJpeg &) = delete;
  CapturedJpeg &operator=(const CapturedJpeg &) = delete;
  ~CapturedJpeg() { free(buf); }
};

// The live view and captures share the camera: it idles at STREAM_FRAMESIZE
// and switches to full resolution only for the length of a capture.
bool cameraBegin();

// Captures one full-resolution JPEG into out, lighting the flash first when
// useFlash is set.
bool cameraCapture(bool useFlash, CapturedJpeg &out);

// Copies the latest live-view frame into buf (grown as needed; the caller
// owns it and frees it with free()). No flash.
bool cameraStreamFrame(uint8_t *&buf, size_t &cap, size_t &len);
