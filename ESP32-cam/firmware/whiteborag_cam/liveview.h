#pragma once

// Always-on live view for aiming the camera: http://LIVEVIEW_HOSTNAME.local/
// (or the board's IP) serves an MJPEG stream at STREAM_FRAMESIZE, no flash.
// There is no auth: anyone on the Wi-Fi can watch.

void liveViewBegin();  // starts the web server; call after wifiBegin()
void liveViewPoll();   // call every loop(); registers the .local name once Wi-Fi is up
