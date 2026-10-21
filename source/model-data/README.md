# Dữ liệu huấn luyện sentiment

Thư mục này chỉ nhận corpus có nguồn, license/quyền sử dụng và manifest rõ ràng.
Không sao chép transcript họp thật, secret, hay bất kỳ dữ liệu/notebook phân loại trầm cảm nào từ `Reports/New_folder/` vào đây.

## Định dạng đầu vào chuẩn

Chuẩn bị ba tệp UTF-8 CSV ngoài Git:

```text
approved/<dataset-version>/train.csv
approved/<dataset-version>/validation.csv
approved/<dataset-version>/test.csv
approved/<dataset-version>/dataset-manifest.json
```

Mỗi tệp cho notebook/script PhoBERT bắt buộc có ba cột `text,label,meeting_id`.
`label` chỉ là `negative`, `neutral` hoặc `positive`; `meeting_id` phải là ID
meeting thật khi đánh giá corpus transcript họp để script có thể chặn leakage giữa
các split.

`dataset-manifest.json` bắt buộc có `dataset_kind` là
`consented-meeting-transcript-sentiment`, version dataset, nguồn,
`license_or_consent`, thời gian thu thập, rule redaction, phiên bản guideline
nhãn, annotation/adjudication policy, split policy, meeting-ID policy và
`output_sha256` cho cả ba CSV. Gate kiểm tra hash trước khi train.
Khởi tạo manifest từ
[`templates/dataset-manifest.example.json`](templates/dataset-manifest.example.json),
rồi thay placeholder bằng metadata và hash thật.

## Quality gate bắt buộc

Chạy lệnh này trước EDA hoặc bất kỳ trainer nào. Lệnh chỉ ghi report tổng hợp,
không ghi text nguồn.

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

Gate dừng khi thiếu manifest/hash, schema, ba nhãn, exact-text leakage hoặc
meeting-ID leakage. Cảnh báo về độ dài và số meeting được lưu trong report để
review trước khi train.

Ví dụ huấn luyện:

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

Lệnh tạo `model.joblib`, `metadata.json` và `evaluation.json`. `evaluation.json` phải được lưu trong evidence bundle và được báo cáo là kết quả trên đúng corpus đó - không được diễn giải thành chất lượng trên transcript họp nếu corpus không phải transcript họp.

Để phục vụ model sau khi artifact đã được duyệt, cấu hình `source/settings.env` như sau:

```text
CLASSIFIER_ADAPTER=tfidf-logreg
MODEL_VERSION=tfidf-logreg-<dataset-version>-v1
MODEL_ARTIFACT_DIR=/models/tfidf-logreg-<dataset-version>-v1
MODEL_ARTIFACT_SHA256=<sha256 của model.joblib>
```

Artifact là file `joblib` và chỉ được nạp từ nguồn tin cậy đã xác minh hash; không nhận artifact do người dùng tải lên.

## PhoBERT trên Google Colab

[`colab/train_meeting_sentiment_phobert.py`](colab/train_meeting_sentiment_phobert.py)
là script fine-tune PhoBERT cho một corpus transcript họp đã được phê duyệt. Script
bắt buộc các cột `text,label,meeting_id`, chặn meeting/text trùng giữa các split,
kiểm tra manifest/hash trước khi tải model, calibrate trên validation và chọn
ngưỡng `unknown` trước khi đánh giá test. Nó chỉ tạo artifact và báo cáo đánh giá;
backend hiện chưa có adapter serving PhoBERT.

Để upload trực tiếp lên Google Colab, dùng
[`MeetingSentiment_PhoBERT_Training_Colab.ipynb`](colab/MeetingSentiment_PhoBERT_Training_Colab.ipynb).
Notebook là bản độc lập của quy trình này: cài dependency, mount Google Drive,
kiểm tra manifest/hash và split, fine-tune, calibration và tạo archive artifact.

Thiết kế đầy đủ từ dữ liệu, artifact, adapter backend đến rollout nằm tại
[`docs/ai-data/CUSTOM_MODEL_MEETING_SENTIMENT.md`](../../docs/ai-data/CUSTOM_MODEL_MEETING_SENTIMENT.md).

## Smoke test từ UIT-VSMEC

[`tools/build_uit_vsmec_proxy.py`](tools/build_uit_vsmec_proxy.py) có thể tạo ba
CSV từ UIT-VSMEC để kiểm tra schema, quá trình fine-tune và artifact trên Colab.
Đó là external emotion-to-polarity **proxy**, không phải dữ liệu transcript họp;
builder ghi limitation này trong manifest và không được dùng metrics proxy để
promote model hoặc báo cáo kết quả cuối. Hướng dẫn chạy ở
[`tools/README.md`](tools/README.md).

## Môi trường local và kiểm tra split

Tạo environment riêng (CPU) ở root dự án khi cần chạy local, không dùng
environment backend:

```bash
uv python install 3.12 --install-dir source/model-data/.python
uv venv .venv \
  --python source/model-data/.python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12
uv pip install --python .venv/bin/python --torch-backend cpu \
  "torch>=2.5" "transformers>=4.46,<5" "datasets>=3,<4" \
  "accelerate>=1,<2" "scikit-learn>=1.4,<2" "underthesea>=6,<9"
```

Sau khi builder tạo ba CSV, kiểm tra bằng chính trainer nhưng không tải model hay
tạo artifact:

```bash
.venv/bin/python source/model-data/colab/train_meeting_sentiment_phobert.py \
  --train <data-dir>/train.csv \
  --validation <data-dir>/validation.csv \
  --test <data-dir>/test.csv \
  --dataset-manifest <data-dir>/dataset-manifest.json \
  --dataset-version <dataset-version> \
  --dataset-profile approved-meeting \
  --model-version <model-version> \
  --quality-report source/model-data/work/<dataset-version>/quality-report.json \
  --validate-only
```
