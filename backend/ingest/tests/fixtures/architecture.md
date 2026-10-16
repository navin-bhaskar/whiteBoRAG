# White BORAH architecture

## Diagram
- Dp32
  - CAM
  - IR sensor
- AWS
  - API gateway
  - pre-sign URL λ
- ESP32 CAM
  - Bucket

Edges:
- Dp32 → API gateway, labelled "AWS key"
- IR sensor → ESP32 CAM, labelled "image"
- Dp32 → ESP32 CAM, labelled "pre-signed URL"

## TODO
- [x] Test transform code
- [x] Deploy lambda du and check for pre-signed URL
- [ ] Finilize IR sensor wave behaviour on ESP32 CAM