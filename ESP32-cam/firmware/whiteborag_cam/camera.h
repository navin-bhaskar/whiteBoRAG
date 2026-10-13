#pragma once

#include "esp_camera.h"

bool cameraBegin();

// Captures one JPEG, lighting the flash first when useFlash is set.
// Returns nullptr on failure; otherwise release it with esp_camera_fb_return().
camera_fb_t *cameraCapture(bool useFlash);
