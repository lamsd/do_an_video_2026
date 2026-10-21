# Custom model cho Meeting Intelligence

> Trạng thái: thiết kế và runbook triển khai. Runtime hiện hành vẫn là
> `baseline-rules-v2`; backend chưa có adapter serving PhoBERT. Không diễn giải
> tài liệu này như bằng chứng model đã chạy hoặc đã đạt một chỉ số chất lượng nào.

## 1. Quyết định đề xuất

Xây dựng `MeetingSentiment-PhoBERT-v1`: PhoBERT cho tiếng Việt với classification
head ba lớp, được fine-tune trên **analysis unit của transcript họp có consent**.

```text
finalized transcript segments
  -> quality gate + language route
  -> 1-3 segments cùng speaker = analysis unit
  -> PhoBERT-base-v2 + 3-class head
  -> calibrated probabilities
  -> negative | neutral | positive | unknown (abstention)
```

`unknown` không là lớp được học. Đó là kết quả an toàn khi unit không đạt quality
gate, ngoài ngôn ngữ hỗ trợ, hoặc confidence thấp hơn threshold đã chọn trên tập
validation. Model không phân loại trầm cảm, trạng thái sức khỏe tâm thần, năng lực,
tính cách hoặc con người.

## 2. Vì sao chọn PhoBERT-base-v2

| Tiêu chí | Quyết định |
| --- | --- |
| Ngôn ngữ chính | Tiếng Việt, giữ dấu và word segmentation tương thích PhoBERT. |
| Mô hình v1 | `vinai/phobert-base-v2` + dropout + linear head 3 lớp. |
| Huấn luyện | Full fine-tune là cấu hình đối chứng; LoRA là tùy chọn khi GPU Colab hạn chế. |
| Inference | Batch theo analysis unit, `max_length=256`; worker riêng, không chạy trong FastAPI request. |
| Độ tin cậy | Temperature scaling trên validation và threshold cho `unknown`. |
| Tính tái lập | Dataset manifest, code commit, seed, tokenizer revision, model checksum và evaluation report. |

PhoBERT-base phù hợp MVP hơn model large: nhỏ hơn, dễ fine-tune trên Colab/T4 và
dễ đo P95 latency. Chỉ cân nhắc model large, quantization hoặc distillation sau khi
có benchmark trên cùng test set. Không giả định rằng các tối ưu này cải thiện chất
lượng hoặc độ trễ nếu chưa đo.

## 3. Hợp đồng input/output

### Input cho model

Model chỉ nhận `analysis_unit` đã qua quality gate:

```json
{
  "text": "văn bản đã chuẩn hóa, giữ dấu tiếng Việt",
  "language": "vi",
  "source_segment_ids": ["seg-1", "seg-2"],
  "speaker_key": "speaker-42",
  "source_revision": 17,
  "preprocessing_version": "2026-09-v1"
}
```

Không nối segment của các speaker khác nhau. Không sửa raw transcript; normalized
text chỉ nằm trong analysis unit. Unit draft, retracted, rỗng, quá ngắn, trùng lặp,
không phải nội dung họp hoặc non-`vi` không được infer và phải có quality reason.

### Output chuẩn

```json
{
  "label": "neutral",
  "confidence": 0.81,
  "probabilities": {"negative": 0.08, "neutral": 0.81, "positive": 0.11},
  "polarity_score": 0.03,
  "model_version": "meeting-sentiment-phobert-v1",
  "inference_ms": 24
}
```

`polarity_score = P(positive) - P(negative)` chỉ phục vụ aggregate timeline; không
thay thế nhãn hoặc confidence. Khi confidence dưới threshold, `label` cuối cùng là
`unknown` nhưng xác suất vẫn được lưu để audit.

## 4. Dữ liệu đúng task

Không dùng các CSV/notebook phân loại trầm cảm trong `Reports/New_folder/tram_cam`
cho model này. Chúng là nhị phân, ngoài domain cuộc họp và không cung cấp split theo
meeting. Cũng không dùng trực tiếp UIT-VSMEC 7 nhãn emotion làm test cuối cho
polarity ba lớp.

Corpus mục tiêu phải có ba file UTF-8 ngoài Git:

```text
source/model-data/approved/<dataset-version>/
  train.csv
  validation.csv
  test.csv
  dataset-manifest.json
```

Mỗi file có `text,label,meeting_id`. `label` chỉ là `negative`, `neutral` hoặc
`positive`; `meeting_id` không được xuất hiện ở nhiều split. Dataset manifest phải
ghi nguồn, license/consent, thời gian thu thập, số meeting/speaker/unit, hash, quy
tắc redaction, label guideline, người annotator và lý do loại unit.

Quality gate đọc `dataset-manifest.json` trước EDA/train. Với profile
`approved-meeting`, manifest phải có `dataset_kind` là
`consented-meeting-transcript-sentiment`, cùng `source`,
`license_or_consent`, `collection_period`, `redaction_policy`,
`label_guideline_version`, `annotation_policy`, `split_policy`,
`meeting_id_policy` và `output_sha256` cho ba split. Hash phải khớp tệp thực tế.

### Quy trình annotation

1. Chốt guideline: polarity của **nội dung transcript**, phủ định, mỉa mai,
   quotation, code-switching và insufficient context.
2. Hai annotator gán nhãn độc lập ở cấp analysis unit.
3. Adjudication cho bất đồng; báo cáo Cohen's kappa hoặc Krippendorff's alpha.
4. Chia train/validation/test theo meeting trước tuning; khóa test set.
5. Lưu split manifest và hash để không đổi test set ngầm giữa các lần chạy.

Mốc pilot hợp lý là 1.000-2.000 unit đã adjudicate ở nhiều meeting. Mục tiêu này
không thay thế yêu cầu phân bố lớp phù hợp và metadata/consent hoàn chỉnh.

## 5. Quy trình train trên Google Colab

Dùng notebook độc lập:

- [`MeetingSentiment_PhoBERT_Training_Colab.ipynb`](../../source/model-data/colab/MeetingSentiment_PhoBERT_Training_Colab.ipynb)
- [`train_meeting_sentiment_phobert.py`](../../source/model-data/colab/train_meeting_sentiment_phobert.py)

Để kiểm tra cơ chế train/artifact trước khi có corpus họp đã consent, có thể tạo
**proxy smoke test** từ UIT-VSMEC bằng
[`build_uit_vsmec_proxy.py`](../../source/model-data/tools/build_uit_vsmec_proxy.py).
Proxy giữ nguồn/split, loại nhãn emotion mơ hồ và sinh manifest cảnh báo. Nó không
phải dataset meeting, không được dùng benchmark cuối hoặc promote vào runtime.
EDA aggregate của proxy và cách chạy lại nằm tại
[`EDA_UIT_VSMEC_PROXY.md`](EDA_UIT_VSMEC_PROXY.md).

Notebook thực hiện các điểm bắt buộc sau:

1. Kiểm tra manifest/hash, schema `text,label,meeting_id` và nhãn đúng ba lớp.
2. Dừng run nếu meeting hoặc exact text trùng giữa split.
3. Word-segment tiếng Việt trước tokenizer PhoBERT, tokenize với `max_length=256`.
4. Fine-tune với seed/version/hyperparameter được ghi lại.
5. Chọn temperature và `unknown_threshold` **chỉ** trên validation.
6. Đánh giá một lần trên test: macro-F1, F1 từng lớp, confusion matrix, coverage,
   unknown rate và accepted macro-F1.
7. Sinh `quality-report.json`, `model/`, `evaluation.json`, `label_mapping.json`, `MODEL_CARD.md` và ZIP
   artifact.

Colab là môi trường huấn luyện, không phải model registry hoặc endpoint production.
Không mount Google Drive công khai và không đưa raw transcript vào notebook output,
log, cell đã share hoặc repository.

## 6. Artifact và registry tối thiểu

```text
meeting-sentiment-phobert-v1/
  model/                    # config, weights, tokenizer
  quality-report.json       # manifest/hash, schema và leakage preflight
  evaluation.json           # validation/test, calibration, threshold
  label_mapping.json
  MODEL_CARD.md
  dataset-manifest.json     # nguồn, consent, split hash, guideline version
  SHA256SUMS
```

Artifact phải immutable sau khi đánh giá. Tạo checksum SHA-256 trên manifest hoặc
archive model, lưu checksum vào registry/evidence và chỉ mount read-only vào worker.
Không nạp artifact do browser upload hoặc nhận từ URL không kiểm tra hash.

Thông tin tối thiểu trong `model_registry`:

| Trường | Ý nghĩa |
| --- | --- |
| `model_version` | ID bất biến, ví dụ `meeting-sentiment-phobert-v1`. |
| `task`, `labels` | `meeting-transcript-polarity-v1`, ba nhãn theo thứ tự cố định. |
| `base_model`, `tokenizer_revision` | Nguồn PhoBERT và tokenizer thực sự đã dùng. |
| `preprocessing_version` | Quy tắc normalize/unit builder tương thích. |
| `artifact_uri`, `sha256` | Vị trí nội bộ tin cậy và checksum. |
| `threshold`, `temperature` | Cấu hình từ validation, không tune bằng test. |
| `dataset_version`, `evaluation_uri` | Truy vết nguồn metrics. |
| `status` | `candidate`, `shadow`, `active`, `retired`. |

## 7. Tích hợp vào backend

Hiện backend có `rules`, `dummy-contract` và `tfidf-logreg`. Thư mục
`source/model-artifacts` đã được mount read-only tại `/models` cho backend và worker;
vì vậy PhoBERT không tự hoạt động chỉ bằng cách đổi `CLASSIFIER_ADAPTER`.

Thay đổi cần triển khai trong một nhánh riêng:

1. Thêm `PhoBertSentimentClassifier` trong
   `source/src/backend/app/analysis/classifier.py`, triển khai đúng
   `SentimentClassifier` protocol.
2. Chỉ nạp artifact local tại `MODEL_ARTIFACT_DIR`; kiểm tra metadata, labels,
   preprocessing/tokenizer revision và SHA-256 trước khi worker ready.
3. Batch units `language == "vi"`; non-`vi` trả `unknown` mà không gọi model.
4. Trả đủ xác suất ba nhãn, `inference_ms`, model version và score; không log text,
   tokens, key hay PII.
5. Thêm config explicit, ví dụ:

   ```dotenv
   CLASSIFIER_ADAPTER=phobert
   MODEL_VERSION=meeting-sentiment-phobert-v1
   MODEL_ARTIFACT_DIR=/models/meeting-sentiment-phobert-v1
   MODEL_ARTIFACT_SHA256=<approved-sha256>
   SENTIMENT_CONFIDENCE_THRESHOLD=<validation-selected-threshold>
   ```

6. Thêm unit tests cho label mapping, unknown threshold, model/hash mismatch,
   non-`vi`, malformed artifact và probability shape.
7. Thêm integration test API -> PostgreSQL -> Valkey -> worker -> analytics với fake
   transformer adapter trước; test model thật chỉ dùng fixture đã được phép.

Không fallback âm thầm sang `rules` khi artifact PhoBERT lỗi. Worker phải fail
readiness rõ ràng để `model_version` trong prediction luôn trung thực.

## 8. Rollout tối ưu và an toàn

```text
candidate artifact
  -> offline locked-test evaluation
  -> shadow run trên meeting đã consent
  -> review metrics + error slices + latency
  -> activate một version bất biến
  -> monitor / rollback về version đã biết
```

Shadow run lưu prediction riêng theo model version, không thay dashboard đang dùng
baseline. Chỉ promote khi model đáp ứng gate đã chốt trên cùng test set, không làm
xấu lớp negative hoặc các lát dữ liệu quan trọng, và inference/queue không làm hỏng
SLO hệ thống đã đo. Rollback chỉ đổi version artifact, không retrain gấp.

Tối ưu theo thứ tự:

1. Batch inference và `max_length=256`.
2. GPU worker riêng khi workload cần; CPU chỉ dùng sau benchmark thực tế.
3. LoRA/adapter trong training để giảm VRAM nếu cần.
4. Quantization hoặc distillation sau khi so sánh chất lượng, calibration và P95
   trên cùng environment.

## 9. Tiêu chí nghiệm thu custom model

| Nhóm | Điều kiện pass |
| --- | --- |
| Dữ liệu | Consent/license, manifest, meeting-level split, test set khóa và annotation agreement. |
| Model | Macro-F1/F1 lớp/confusion matrix trên locked test; calibration, coverage và unknown rate được báo cáo. |
| Artifact | Version, checksum, tokenizer, threshold, seed và evaluation report truy vết được. |
| Backend | Hash mismatch fail-closed; output đúng schema; model version lưu theo prediction/run. |
| Runtime | Readiness, batch inference, retry/idempotency, P95/queue lag đo từ log thật. |
| E2E | Google Meet/Vexa -> final transcript -> PhoBERT worker -> dashboard evidence có consent. |
| An toàn | Không raw transcript/secrets trong Git/log/evidence; không claim chẩn đoán hoặc đánh giá con người. |

## 10. Lộ trình ngắn nhất

1. Hoàn thiện E2E Google Meet/Vexa và evidence hệ thống với baseline hiện tại.
2. Thu thập/gán nhãn corpus sentiment họp có consent; tạo manifest và split theo meeting.
3. Chạy TF-IDF + Logistic Regression làm baseline và notebook PhoBERT trên cùng test.
4. Review report; chỉ chọn threshold/temperature từ validation.
5. Thêm PhoBERT adapter, test contract và shadow run.
6. Promote/rollback qua artifact version; cập nhật Chương 4/8 bằng số liệu thật.

## 11. Không thuộc phạm vi v1

- Sàng lọc hoặc chẩn đoán trầm cảm/sức khỏe tâm thần.
- Emotion đa nhãn, sarcasm detection độc lập hoặc prediction cho ngôn ngữ ngoài tiếng Việt.
- Tự động quyết định nhân sự, giáo dục, kỷ luật hoặc xếp hạng người tham gia.
- Huấn luyện lại tự động từ transcript vận hành hoặc feedback chưa adjudicate.
