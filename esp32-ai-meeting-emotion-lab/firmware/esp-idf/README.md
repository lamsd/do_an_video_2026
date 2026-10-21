# ESP-IDF firmware target

Đây là target ESP-IDF chính; `../src/main.cpp` và `../platformio.ini` được giữ làm đường phát triển PlatformIO tương thích. Mỗi board phải có defaults riêng ngoài Git:

```bash
cd firmware/esp-idf
cp config/esp32-01.defaults.example config/esp32-01.defaults
idf.py -DSDKCONFIG_DEFAULTS="sdkconfig.defaults;config/esp32-01.defaults" set-target esp32
idf.py build flash monitor
```

Lặp lại đúng mapping `01/empathy`, `02/critical`, `03/optimistic`, `04/moderator`. Các file `*.defaults` thực chứa password đã bị `.gitignore`; không commit chúng. Với triển khai thật, dùng `mqtts://`, kiểm tra CA certificate/mTLS và không để password vào artifact build dùng chung.

Nguồn dưới đây có Wi-Fi, LWT, MQTT, state machine và relay control-plane; nó không xử lý microphone, loa, TTS, GPT hoặc emotion inference.
