# Cài đặt, cấu hình và chạy Meeting Intelligence

Tài liệu này áp dụng cho stack mới trong `source/compose.yaml`. Mọi secret chỉ nằm trong `source/settings.env` (permission `600`) hoặc secret manager; dashboard không nhận, không hiển thị và không ghi secret.

## 0. Điều kiện trước khi bắt đầu

- Docker Engine và Docker Compose v2 đang chạy.
- Có Vexa meetings-only self-host stack và dịch vụ transcription mà Vexa gọi được.
- Chỉ dùng Google Meet test khi tất cả người tham gia đồng ý cho bot vào cuộc họp.
- Không copy API key vào chat, Git, browser DevTools, ảnh chụp màn hình hoặc tài liệu luận văn.

Nếu key đã từng xuất hiện trong editor/chat, coi key đó là đã lộ: mint key mới ở Bước 3 và thay thế key cũ.

## 1. Tạo file cấu hình cục bộ (chỉ lần đầu)

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
chmod 755 scripts/bootstrap.sh scripts/vexa-selfhost.sh scripts/runtime-settings.sh
./scripts/bootstrap.sh
chmod 600 settings.env
```

Mở `settings.env` cục bộ để điền các giá trị hạ tầng ban đầu: `POSTGRES_PASSWORD`, các `DB_*`/`MINIO_*`, `ADMIN_TOKEN`, `INTERNAL_API_SECRET`, `VEXA_NETWORK` và transcription endpoint. Không commit file này.

Tạo các secret Vexa/app nếu file mới còn `CHANGE_ME`:

```bash
./scripts/generate-selfhost-secrets.sh
```

Script in secret duy nhất vào terminal. Điền chúng vào `settings.env`, không lưu output vào file log.

## 2. Khởi động và kiểm Vexa self-host

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/vexa-selfhost.sh check
./scripts/vexa-selfhost.sh start
./scripts/vexa-selfhost.sh verify
```

`verify` chỉ pass khi gateway healthy và bot-runner image đã có. Nếu nó báo thiếu image, chạy đúng lệnh `docker pull …` mà script in ra, sau đó chạy lại `verify`.

## 3. Cấp hoặc rotate Vexa API key

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/vexa-selfhost.sh mint-token
```

Token chỉ xuất hiện một lần. Sao chép nó từ terminal, sau đó chạy ngay wizard sau. Không dán token trực tiếp vào dashboard hoặc vào lệnh shell.

```bash
./scripts/runtime-settings.sh wizard
```

Wizard sẽ:

1. Hỏi `VEXA_API_KEY` bằng input ẩn và kiểm tra prefix `vxa_`.
2. Hỏi adapter `rules` hoặc `tfidf-logreg`.
3. Hỏi model version, preprocessing version và confidence threshold.
4. Nếu chọn `tfidf-logreg`, bắt buộc directory artifact đã mount dưới `/models` và SHA-256 64 ký tự.

Nếu chỉ cần thay key mà không đổi model, dùng:

```bash
./scripts/runtime-settings.sh configure-vexa
```

## 4. Build/restart đúng cách

Sau khi thay bất cứ giá trị nào trong `settings.env`, dùng:

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/runtime-settings.sh apply
```

Lệnh này kiểm Compose, build image mới và force-recreate `backend`, `worker`, `dashboard`. PostgreSQL và Valkey giữ nguyên volume/dữ liệu. Không thay bằng `docker compose restart`: lệnh restart không nạp lại `env_file`.

## 5. Xác minh và mở dashboard

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/verify.sh
./scripts/runtime-settings.sh status
```

Mở `http://127.0.0.1:<DASHBOARD_PORT>` — môi trường hiện tại dùng `http://127.0.0.1:3001/`. Hard refresh bằng `Ctrl+Shift+R`.

Trong panel **Cấu hình, model và tích hợp**, chạy theo 5 bước hiển thị. Các nút chỉ sao chép lệnh vào clipboard; đây là chủ đích an toàn vì browser không được quyền sửa `settings.env` hoặc dùng Docker socket.

## 6. Chạy Google Meet test sau khi setup pass

1. Trong dashboard, dán URL đúng dạng `https://meet.google.com/abc-defg-hij`.
2. Tick xác nhận consent của người tham gia.
3. Chọn **Yêu cầu bot tham gia**.
4. Chờ 30–90 giây, rồi host admit bot trong Google Meet.
5. Khi có transcript final, bấm **Chạy model đang cấu hình**.

Nếu bot không xuất hiện, kiểm lại Bước 2–5 trước; dashboard không thể bypass việc host duyệt bot.

## Kiểm tra nhanh khi có lỗi

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/runtime-settings.sh guide
./scripts/runtime-settings.sh status
docker compose --env-file settings.env ps
docker compose --env-file settings.env logs --tail=100 backend worker
./scripts/verify.sh
```

Không dùng `docker compose down -v` khi xử lý thông thường vì lệnh này xóa PostgreSQL/Valkey volumes.
