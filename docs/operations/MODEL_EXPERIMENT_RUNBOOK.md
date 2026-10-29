# Runbook thực nghiệm model và triển khai đa nền tảng

Runbook này dành cho stack chuẩn ở `source/`. Nó không dùng ESP32, firmware hay dữ liệu audio edge. Mục tiêu là tạo các analysis run có thể truy vết, so sánh vận hành model trên cùng transcript revision và chuẩn bị benchmark có ground truth.

## Phạm vi và điều kiện dừng

- Google Meet + Vexa là integration platform đã có. Zoom, Teams hay Jitsi cần adapter, sandbox/API, consent và E2E evidence riêng trước khi được so sánh.
- Chỉ phân tích polarity transcript: `positive`, `neutral`, `negative`, `unknown`; không suy luận sức khỏe tâm thần hoặc đánh giá người tham gia.
- Không đưa raw transcript, corpus được phê duyệt, artifact model hay `settings.env` vào Git.
- Không đưa UIT-VSMEC proxy hay corpus phân loại trầm cảm vào kết quả benchmark transcript họp.

## 1. Chuẩn bị corpus thật

Trước khi huấn luyện hoặc tính Macro-F1, cần có transcript được phép sử dụng, guideline nhãn ba lớp, hai annotator độc lập và adjudication. Tạo ba CSV ở vùng local đã bị `.gitignore`:

```text
source/model-data/approved/<dataset-version>/train.csv
source/model-data/approved/<dataset-version>/validation.csv
source/model-data/approved/<dataset-version>/test.csv
source/model-data/approved/<dataset-version>/dataset-manifest.json
```

Mỗi CSV bắt buộc có `text,label,meeting_id`. Split theo `meeting_id`, khóa test set trước tuning, hoàn thiện manifest/hash và chạy quality gate trước mọi trainer:

```bash
.venv/bin/python source/model-data/tools/check_meeting_dataset_quality.py \
  --train source/model-data/approved/<dataset-version>/train.csv \
  --validation source/model-data/approved/<dataset-version>/validation.csv \
  --test source/model-data/approved/<dataset-version>/test.csv \
  --dataset-manifest source/model-data/approved/<dataset-version>/dataset-manifest.json \
  --dataset-version <dataset-version> \
  --dataset-profile approved-meeting \
  --report source/model-data/work/<dataset-version>/quality-report.json
```

`approved/` và `work/` vẫn là local-only. Chỉ report tổng hợp, hash và evidence đã redaction được đưa vào hồ sơ thực nghiệm.

## 2. Các model hiện hỗ trợ

| Biến thể | Trạng thái | Dùng để làm gì | Không được kết luận |
| --- | --- | --- | --- |
| `rules` / `baseline-rules-v2` | Có sẵn | Smoke test API → queue → worker → dashboard | Chất lượng sentiment |
| `tfidf-logreg` | Có adapter, cần artifact đã duyệt | Baseline CPU tái lập trên corpus đã gán nhãn | Hiệu quả meeting nếu dùng corpus ngoài domain |
| Checkpoint PhoBERT có sẵn | Chưa có adapter serving | Đối tượng benchmark sau khi thêm adapter/hash/label mapping | Không đổi config để gọi là đã chạy |

Không dùng `dummy-contract` để so sánh chất lượng; nó chỉ kiểm tra interface adapter.

## 3. Tạo baseline TF--IDF có truy vết

Sau quality gate, tạo artifact local từ cùng corpus:

```bash
cd source/src/backend
uv run python scripts/train_tfidf_logreg.py \
  --train ../../model-data/approved/<dataset-version>/train.csv \
  --validation ../../model-data/approved/<dataset-version>/validation.csv \
  --test ../../model-data/approved/<dataset-version>/test.csv \
  --dataset-manifest ../../model-data/approved/<dataset-version>/dataset-manifest.json \
  --dataset-version <dataset-version> \
  --model-version tfidf-logreg-<dataset-version>-v1 \
  --output ../../model-artifacts/tfidf-logreg-<dataset-version>-v1
```

Lưu `evaluation.json`, `quality-report.json`, `metadata.json` và SHA-256 của `model.joblib` trong evidence bundle đã redaction. Không activate artifact tạo từ proxy smoke test.

## 4. Tạo run trên cùng transcript revision

Một model được chọn bằng cấu hình container. Trước khi đổi model, để các job hiện có hoàn tất hoặc ghi nhận trạng thái của chúng. Không đổi cấu hình giữa lúc worker đang xử lý một run.

1. Chạy model đầu tiên (ví dụ `rules`) và lưu `analysis_run_id`/Evidence ID.
2. Cập nhật các trường dưới đây trong `source/settings.env` cho TF--IDF:

   ```dotenv
   CLASSIFIER_ADAPTER=tfidf-logreg
   MODEL_VERSION=tfidf-logreg-<dataset-version>-v1
   MODEL_ARTIFACT_DIR=/models/tfidf-logreg-<dataset-version>-v1
   MODEL_ARTIFACT_SHA256=<sha256-của-model.joblib>
   ```

3. Khởi động lại **cả** backend và worker để API tạo run với version đúng, còn worker nạp artifact đã kiểm tra hash:

   ```bash
   cd source
   docker compose --env-file settings.env restart backend worker
   ```

4. Gửi `POST /v1/meetings/<MEETING_ID>/analysis?kind=backfill` cho đúng meeting. Với một transcript revision, run mới có model version khác sẽ được lưu cạnh run cũ, không ghi đè evidence.
5. Mở dashboard, chọn lần chạy trong combobox. Bảng `Các model đã chạy` chỉ so sánh unit, coverage và batch duration; để kết luận model tốt hơn phải dùng `evaluation.json` trên locked test.

Worker fail-closed nếu một job đang chờ yêu cầu `model_version` khác artifact đang chạy. Lỗi `model_runtime_mismatch` là tín hiệu cần restart với cấu hình phù hợp hoặc tạo lại run sau khi xác nhận config, không phải lỗi để bỏ qua.

## 5. Đo nhiều nền tảng tính toán

Mỗi hàng đo dùng cùng Git commit/image digest, artifact SHA-256, dataset/test hash, warm-up, batch size, concurrency và workload generator.

| Target | Giữ cố định | Thu thập |
| --- | --- | --- |
| Docker CPU máy DEV | image + model + workload | P50/P95/P99, throughput, RAM, queue lag, failure/retry |
| Docker CPU máy UAT | như trên, secret riêng | các metric trên và smoke/E2E pass |
| Worker GPU riêng | như trên, thêm batch size | các metric trên, VRAM/GPU utilization |

Không so sánh GPU với CPU bằng một batch duration duy nhất trên dashboard. Chạy nhiều lần, lưu thời điểm warm-up, rồi tính percentile từ log đã redaction. Portable deployment giữa các máy thực hiện theo [`MULTI_MACHINE_PORTABLE_DEPLOYMENT.md`](../deployment/MULTI_MACHINE_PORTABLE_DEPLOYMENT.md); mỗi máy có secret, Vexa token và volume riêng.

## 6. Evidence tối thiểu cho mỗi hàng đo

Mỗi run cần một Evidence ID và các trường: Git commit/image digest, target CPU/GPU, Docker/driver, `CLASSIFIER_ADAPTER`, resolved `MODEL_VERSION`, artifact hash, preprocessing version, dataset/test hash, command, exit code, workload, warm-up, sample count, `analysis_run_id`, pass/fail và limitation. Chỉ sau đó mới chuyển số liệu vào Chương 8.
