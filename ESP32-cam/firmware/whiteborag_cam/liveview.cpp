#include "liveview.h"

#include <Arduino.h>
#include <ESPmDNS.h>
#include <WiFi.h>

#include "camera.h"
#include "config.h"
#include "esp_http_server.h"

static httpd_handle_t server = nullptr;
static bool mdnsUp = false;

static const char PAGE[] =
    "<!doctype html><html><head><meta charset=utf-8>"
    "<meta name=viewport content='width=device-width,initial-scale=1'>"
    "<title>WhiteBorag live view</title>"
    "<style>body{margin:0;background:#111;color:#ccc;font:14px sans-serif;text-align:center}"
    "img{display:block;max-width:100%;height:auto;margin:0 auto}</style></head><body>"
    "<p>Live view. Frame the whole board; it pauses for a moment during each capture.</p>"
    "<img src='/stream' alt='camera live view'></body></html>";

static esp_err_t pageHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, PAGE, HTTPD_RESP_USE_STRLEN);
}

// MJPEG: one multipart part per frame until the viewer leaves. Frames are
// copied out first so a slow viewer never holds up a capture. The server has
// one worker task, so a second viewer waits until this one leaves.
static esp_err_t streamHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  Serial.println("[live] viewer connected");

  uint8_t *frame = nullptr;
  size_t cap = 0, len = 0;
  char head[96];
  esp_err_t res = ESP_OK;
  while (res == ESP_OK) {
    if (!cameraStreamFrame(frame, cap, len)) {
      delay(100);  // e.g. mid-switch after a capture; try the next frame
      continue;
    }
    int n = snprintf(head, sizeof head,
                     "\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n",
                     (unsigned)len);
    res = httpd_resp_send_chunk(req, head, n);
    if (res == ESP_OK) res = httpd_resp_send_chunk(req, (const char *)frame, len);
  }
  free(frame);
  Serial.println("[live] viewer gone");
  return res;  // the failed send means the viewer left; the server closes the socket
}

void liveViewBegin() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.stack_size = 8192;
  if (httpd_start(&server, &cfg) != ESP_OK) {
    Serial.println("[live] web server failed to start");
    server = nullptr;
    return;
  }
  httpd_uri_t page = {"/", HTTP_GET, pageHandler, nullptr};
  httpd_uri_t stream = {"/stream", HTTP_GET, streamHandler, nullptr};
  httpd_register_uri_handler(server, &page);
  httpd_register_uri_handler(server, &stream);
}

void liveViewPoll() {
  if (mdnsUp || !server || WiFi.status() != WL_CONNECTED) return;
  mdnsUp = true;  // one attempt; the IP address still works if it fails
  if (MDNS.begin(LIVEVIEW_HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
  } else {
    Serial.println("[live] mDNS failed; use the IP address");
  }
  Serial.printf("[live] live view at http://%s.local/ or http://%s/\n", LIVEVIEW_HOSTNAME,
                WiFi.localIP().toString().c_str());
}
