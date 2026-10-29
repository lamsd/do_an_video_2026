# Kế hoạch nghiệm thu ứng dụng và Dashboard

Mục tiêu của giai đoạn này là chứng minh người dùng có thể vận hành hệ thống Meeting Intelligence một cách truy vết được: mở đúng meeting, xem đúng analysis run, hiểu coverage/giới hạn, kiểm evidence và bàn giao trạng thái kỹ thuật an toàn. Đây **không** là giai đoạn xây model, gán nhãn dữ liệu, hay công bố accuracy/F1/WER.

Phạm vi mã nguồn duy nhất là `source/compose.yaml`, `source/src/backend` và `source/src/dashboard`. Không dùng `source/meeting-intelligence-backend` (legacy) cho demo hay UAT.

## 1. Yêu cầu chấp nhận

| ID | Yêu cầu hướng người dùng/vận hành | Cách chấp nhận |
| --- | --- | --- |
| FR-01 | Người dùng mở được meeting mới nhất hoặc một Application Meeting UUID hợp lệ. | Dashboard tải meeting và hiển thị UUID/trạng thái; UUID sai hiện lỗi thay vì dữ liệu của meeting khác. Form tạo meeting tách biệt với ô UUID, chỉ gửi bot sau khi người dùng xác nhận consent. |
| FR-02 | Người dùng biết output thuộc lần chạy nào. | Chọn được `analysis run`; UI hiện run ID, model/adapter version, preprocessing version và transcript revision. |
| FR-03 | Người dùng không diễn giải thiếu dữ liệu thành trung tính. | UI hiện số unit predicted/accepted/total, prediction coverage, effective coverage, `unknown`/quality reason. |
| FR-04 | Người dùng đối chiếu được aggregate với evidence. | Timeline, speaker aggregate và evidence đều dùng cùng run đang chọn; chọn một cột timeline chỉ lọc evidence thuộc cửa sổ đó, với bộ lọc nhãn/confidence và nút tải thêm. |
| FR-05 | Người vận hành có thể bàn giao trạng thái mà không làm lộ nội dung họp. | Nút **Sao chép tóm tắt** chỉ chứa UUID, run/version/revision, coverage và batch duration; không chứa transcript, tên speaker hoặc secret. |
| OR-01 | Stack chạy lặp lại được trên máy DEV/UAT. | `docker compose --env-file settings.env up -d --build`, `/ready` và dashboard đều pass. |
| OR-02 | Một lần nghiệm thu có bằng chứng và không xuất raw transcript. | `runtime-status.sh`, `smoke-analysis-pipeline.sh` và `dashboard-acceptance.sh` có exit code/log; ảnh dashboard được che nội dung nhạy cảm. |
| OR-03 | Không công bố dashboard ra Internet khi chưa có kiểm soát production. | Chỉ bind loopback; trước production cần TLS, authentication/authorization, backup/restore và retention policy. |
| OR-04 | Người vận hành kiểm tra/cập nhật cấu hình mà không lộ secret trên web. | Dashboard chỉ trả trạng thái boolean/safe model fields; `runtime-settings.sh` nhập secret kín tại terminal và force-recreate đúng service. |

Các số đo hiện trên dashboard là **trạng thái của một analysis run**. `Batch inference` không phải P95; coverage không phải độ chính xác; polarity transcript không phải đánh giá con người.

## 2. Tiện ích đã bổ sung

- Dashboard có khối **Tóm tắt bàn giao đã lược bỏ transcript**. Người demo bấm sao chép để đưa cho giảng viên/người hỗ trợ mà không phải gửi transcript hay ảnh chứa evidence.
- Timeline là điều khiển truy vết: bấm một cột để giới hạn evidence vào đúng phút đã tổng hợp, bấm **Hiện tất cả evidence** để bỏ giới hạn. Danh sách tải 100 evidence mỗi lần và công khai khi còn có thể tải thêm; nút **Làm mới dữ liệu** cùng thời điểm tải gần nhất giúp người demo chủ động kiểm tra trạng thái.
- Dashboard có form **Yêu cầu bot tham gia** nhận Google Meet URL (cả dạng trực tiếp và `/meet/`), tách hẳn với ô Application Meeting UUID. Người dùng phải tick xác nhận consent trước khi form gọi API; khi thành công, dashboard tự mở UUID vừa tạo để tránh dán nhầm URL Meet vào ô UUID.
- `source/scripts/dashboard-acceptance.sh` kiểm tra read-only: Compose, `/ready`, HTML dashboard; nếu truyền Application Meeting UUID thì kiểm tiếp analysis run mới nhất đã `succeeded` và các trường dashboard phải có. Script không gọi endpoint transcript/evidence và không in `settings.env`.
- Dashboard có **Cấu hình, model và tích hợp**: hiển thị model, threshold, polling/retry và trạng thái Vexa/transcription/artifact nhưng tuyệt đối không trả API key, webhook secret, API URL nội bộ hoặc artifact path. Hai nút chỉ sao chép lệnh setup/apply; browser không có quyền ghi `settings.env` hay điều khiển Docker.
- `runtime-settings.sh` là entry point cấu hình cục bộ có thể mở rộng: thêm tích hợp mới vào `app/api/operator_settings.py` bằng trạng thái an toàn, sau đó thêm prompt/validation tương ứng vào script hoặc secret manager.

## 3. Thực hiện theo thứ tự

### Bước 0 — Chuẩn bị và giới hạn dữ liệu

1. Chỉ dùng Google Meet test có sự đồng ý của người tham gia nếu chạy E2E thật.
2. Không đặt `settings.env`, API key, transcript hay ảnh evidence chưa che thông tin vào Git.
3. Không chạy `docker compose down -v`; lệnh đó xóa dữ liệu PostgreSQL/Valkey.

### Bước 1 — Khởi tạo cấu hình máy

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/bootstrap.sh
chmod 600 settings.env
docker compose --env-file settings.env config --quiet
```

Điền secret cục bộ trong `settings.env`; terminal không nên in giá trị của file này. Sau khi mint replacement Vexa key, dùng wizard để nhập kín key/model thay vì dán vào browser:

```bash
chmod 755 scripts/runtime-settings.sh
./scripts/runtime-settings.sh wizard
```

Nếu dùng Google Meet/Vexa, hoàn thành kiểm tra Vexa và transcription trong [DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md](DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md) trước Bước 2.

### Bước 2 — Build và kiểm tra hạ tầng ứng dụng

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
docker compose --env-file settings.env up -d --build
./scripts/runtime-status.sh
./scripts/verify.sh
```

**Pass:** backend `/ready` và dashboard trả HTTP 200; PostgreSQL và Valkey healthy. Nếu không pass, dừng ở đây và xử lý log/readiness trước khi có buổi demo.

Khi chỉ thay `settings.env` sau lần build đầu, chạy `./scripts/runtime-settings.sh apply`; không dùng riêng `docker compose restart` vì restart không nạp lại `env_file`.

### Bước 3 — Kiểm chứng pipeline bằng dữ liệu tổng hợp

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/smoke-analysis-pipeline.sh
```

**Pass:** lệnh in `PASS: synthetic fixture completed API -> queue -> worker -> analytics API.` Fixture được tự xóa; đây là kiểm chứng integration, không là điểm chất lượng model.

### Bước 4 — Chạy một luồng người dùng thật có consent (tùy chọn nhưng nên có)

1. Tạo bot cho một Google Meet test theo [DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md](DEV_INSTALL_RUN_TEST_DASHBOARD_GUIDE.md).
2. Chỉ tiếp tục sau khi endpoint transcript có segment `is_final=true`.
3. Gọi final analysis qua API hoặc nút **Chạy model đang cấu hình** trên dashboard.
4. Lưu Application Meeting UUID do backend trả về, không dùng mã Google Meet làm UUID dashboard.

### Bước 5 — Nghiệm thu dashboard cùng người dùng

1. Mở URL dashboard ở loopback; mặc định là `http://127.0.0.1:3000`.
2. Xác nhận UUID, trạng thái meeting và run đã chọn trước khi đọc KPI.
3. Kiểm `model/adapter version`, `preprocessing version`, revision, predicted/accepted/total, coverage và batch duration.
4. Chọn một point timeline, kiểm evidence tương ứng và thử bộ lọc nhãn/confidence. Khi coverage thấp hoặc `unknown`, ghi nhận là **không đủ dữ liệu**, không thay bằng neutral.
5. Bấm **Sao chép tóm tắt**. Dán vào một text editor và kiểm tra không có transcript, tên speaker, token hay password.

### Bước 6 — Lưu bằng chứng UAT không lộ nội dung họp

```bash
cd /home/lamsd/Documents/Buildkhoaluan/source
./scripts/dashboard-acceptance.sh "<APPLICATION_MEETING_UUID>"
```

**Pass:** script in `PASS: dashboard acceptance data is complete (no transcript was requested).` Nó chỉ chấp nhận run mới nhất ở trạng thái `succeeded`, giúp tránh chụp dashboard khi worker còn queued/running.

Lưu exit code, timestamp, commit/image digest, phiên bản model/adapter, preprocessing, revision, coverage và ảnh dashboard đã che nội dung. Có thể dùng `./scripts/capture-evidence.sh integration EVID-YYYYMMDD-INT01` cho smoke integration; không đưa UUID thật/raw transcript vào Git.

### Bước 7 — Quyết định nghiệm thu

Chấp nhận MVP khi FR-01 đến FR-05 và OR-01 đến OR-02 đều pass. OR-03 là điều kiện chặn production công khai, không chặn demo loopback. Một lỗi transcript/STT, webhook hoặc run failed phải được ghi là fail/giới hạn; không thay bằng claim về khả năng của model.

## 4. Kịch bản kiểm tra ngắn cho buổi demo

| Thời điểm | Thao tác | Kết quả cần thấy |
| --- | --- | --- |
| Trước demo | `runtime-status.sh` + `verify.sh` | Stack/port/readiness rõ ràng, không in secret. |
| Trước dữ liệu thật | `smoke-analysis-pipeline.sh` | Pipeline nội bộ pass với fixture tổng hợp. |
| Trong demo | Chọn UUID, final analysis, dashboard tự refresh | Run `succeeded`; timeline/evidence khớp run/revision. |
| Bàn giao | Sao chép tóm tắt + `dashboard-acceptance.sh` | Chỉ trạng thái kỹ thuật được chia sẻ; không transcript. |

## 5. Chưa thuộc giai đoạn này

Không bổ sung training/fine-tuning, annotation workflow, benchmark model, WER/CER, SLA/P95, HR/mental-health scoring, auto-alert, Zoom/Teams/Jitsi hay public production. Mỗi hạng mục đó cần phạm vi, consent và protocol kiểm chứng riêng.
