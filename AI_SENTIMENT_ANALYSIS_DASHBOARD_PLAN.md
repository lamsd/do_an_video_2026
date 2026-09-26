# Kế hoạch AI phân tích transcript, cảm xúc và dashboard

> Trạng thái: nền tảng MVP đã triển khai và kiểm chứng end-to-end; PhoBERT fine-tune chưa triển khai.  
> Phạm vi: mở rộng `source/meeting-intelligence-backend` trên luồng Vexa đã có.  
> Mục tiêu MVP: từ transcript đã hoàn tất, tạo được phân tích cảm xúc có bằng chứng, tổng hợp theo người nói/cuộc họp và hiển thị trên dashboard.

## Trạng thái triển khai đã kiểm chứng

Ngày kiểm chứng: 2026-09-20. Luồng sau đã chạy thành công trên local Compose:

```text
Vexa active meeting → backend sync → PostgreSQL → Valkey Stream → AI worker
→ analysis run completed → dashboard tại localhost:3000
```

Kết quả của phiên kiểm thử application meeting `adc9fca1-337b-4dcd-b859-28baad1bf853`:

| Hạng mục | Kết quả |
|---|---|
| Transcript lưu bởi backend | 13 segments, 12 finalized |
| Final analysis run | `succeeded` |
| Analysis units | 6 units |
| Units qua quality gate | 4 units |
| Coverage | 66.7% |
| Model runtime | `baseline-rules-v1` |
| UI | KPI, timeline, evidence và SSE refresh tại `http://localhost:3000` |

`baseline-rules-v1` chỉ là classifier deterministic để kiểm chứng data contract, quality gate, queue và dashboard. Nó **không** phải PhoBERT và không được dùng để kết luận chất lượng mô hình. PhoBERT chỉ được promote sau các bước annotation, benchmark và evaluation ở Phase E.

### Runbook sử dụng MVP hiện tại

1. Khởi động các service tại `source/meeting-intelligence-backend`:

   ```bash
   docker compose up -d --build
   curl -fsS http://localhost:8088/health
   ```

2. Tạo meeting **một lần** qua `POST /v1/meetings`, rồi lưu `id` UUID do backend trả về. Không dùng native Google Meet code như `abc-defg-hij` làm dashboard ID và không tạo bot lần hai nếu Vexa báo active meeting conflict.

3. Admit bot, nói thử, rồi sync transcript:

   ```bash
   curl -X POST http://localhost:8088/v1/meetings/<application-uuid>/sync \
     -H 'X-App-User-Id: local-dev'
   ```

4. Kiểm tra `total > 0` và xem snapshot qua `GET /v1/meetings/<application-uuid>/transcript`.

5. Chạy final analysis:

   ```bash
   curl -X POST 'http://localhost:8088/v1/meetings/<application-uuid>/analysis?kind=final' \
     -H 'X-App-User-Id: local-dev'
   ```

6. Mở `http://localhost:3000`, nhập application UUID và kiểm tra overview, timeline, evidence.

Nếu dashboard trả `502`, kiểm tra backend container trước (`docker compose ps`, `docker compose logs --tail=100 backend`). Nếu trả `404 meeting not found`, UUID chưa tồn tại trong application database. `total: 0` sau sync nghĩa là Vexa chưa trả segment transcript finalized; đây là vấn đề capture/STT upstream, không phải model/dashboard.

## 1. Bối cảnh hiện tại và phạm vi triển khai

Luồng hiện hữu đã nhận transcript từ Vexa, lưu `transcript_segments` vào PostgreSQL, phát SSE và chạy polling reconciliation. Đây là nền tảng đúng để bổ sung AI:

```text
Google Meet → Vexa/STT → Backend ingest/reconcile → PostgreSQL
                                                     │
                                      final segment  │
                                                     ▼
                                              AI job queue
                                                     │
                         ┌───────────────────────────┼───────────────────────────┐
                         ▼                           ▼                           ▼
                  kiểm tra chất lượng         PhoBERT classifier           aggregation
                         │                           │                           │
                         └───────────────────────────┴──────────────► Dashboard/API
```

MVP chỉ phân tích **cảm xúc được biểu đạt trong nội dung lời nói**, không suy luận sức khỏe tâm thần, tính cách, mức độ đáng tin cậy hoặc cảm xúc thật của người tham gia. Kết quả là hỗ trợ rà soát cuộc họp, luôn kèm độ tin cậy và đoạn transcript làm bằng chứng.

### Quan sát từ transcript mẫu

`transcript.json` có đoạn tiếng Việt xen tiếng Anh/Tây Ban Nha/… và nhiều câu không thuộc nội dung họp (ví dụ lời bài hát hoặc lời kêu gọi đăng ký kênh). Vì vậy, đưa thẳng mọi segment vào PhoBERT sẽ làm sai kết quả. Pipeline cần có:

1. Phân loại/ngưỡng ngôn ngữ trước khi chạy model tiếng Việt.
2. Loại hoặc gắn cờ segment quá ngắn, lặp, rỗng, âm nhạc/quảng cáo và lỗi STT.
3. Gộp các segment liền kề cùng người nói thành một `analysis unit`; tránh dự đoán từ câu 1–3 từ.
4. Không tạo nhãn khi dữ liệu không đủ tốt; hiển thị `unknown` thay vì ép kết quả.

## 2. Lý thuyết và định nghĩa bài toán

### 2.1 Sentiment không phải emotion

| Khái niệm | Ý nghĩa | Áp dụng trong MVP |
|---|---|---|
| Sentiment polarity | Sắc thái đánh giá: tích cực, trung tính, tiêu cực | Bài toán bắt buộc, dễ đo lường và phù hợp dashboard |
| Emotion category | Loại cảm xúc: vui, buồn, tức giận, lo lắng, ngạc nhiên… | Pha sau hoặc chạy song song khi đã có dữ liệu gán nhãn đủ tốt |
| Sentiment score | Giá trị liên tục, ví dụ `[-1, 1]` | Suy ra từ xác suất lớp để vẽ xu hướng, không thay thế nhãn gốc |
| Confidence | Độ chắc chắn của model cho dự đoán | Dùng để lọc/tô nhạt, không diễn giải là độ đúng tuyệt đối |

Khuyến nghị MVP dùng 3 nhãn `positive`, `neutral`, `negative`, thêm `unknown` cho trường hợp bị loại bởi quality gate hoặc confidence thấp. Sau khi baseline ổn định mới mở rộng emotion đa nhãn, ví dụ `joy`, `sadness`, `anger`, `fear/anxiety`, `surprise`, `disgust`, `neutral`. Nhãn đa cảm xúc nên cho phép nhiều nhãn trên một unit, vì một câu có thể vừa lo lắng vừa tiêu cực.

### 2.2 Đơn vị dự đoán và đơn vị hiển thị

- **Segment nguồn:** một bản ghi Vexa, dùng làm bằng chứng và để truy vết timestamp.
- **Analysis unit:** 1–3 segment finalized liền nhau của cùng người nói, giới hạn 10–45 giây hoặc 20–180 token. Đây là đầu vào model.
- **Window thời gian:** cửa sổ 30–60 giây để dashboard vẽ xu hướng; trọng số theo confidence và số token.
- **Meeting aggregate:** tổng hợp sau khi họp kết thúc. Không dùng trung bình đơn thuần: một câu dài cần có trọng số lớn hơn câu “ừ”.

Điểm polarity gợi ý:

```text
score = P(positive) - P(negative)      # phạm vi [-1, 1]
weight = token_count × confidence
window_score = sum(score × weight) / sum(weight)
```

Chỉ tính những dự đoán có `confidence >= threshold` (ví dụ 0.60 trong giai đoạn đầu) và `quality_status = accepted`. Lưu cả xác suất từng lớp để có thể thay đổi công thức aggregate mà không chạy model lại.

### 2.3 PhoBERT và hai hướng model

PhoBERT là encoder Transformer tiền huấn luyện cho tiếng Việt. Khi phân loại sentiment, văn bản được tokenize theo tokenizer đi kèm checkpoint, qua PhoBERT, sau đó head classification tạo logits/xác suất nhãn. Không tự thay tokenizer của PhoBERT bằng tokenizer khác.

| Hướng | Mô tả | Khi nên dùng | Quyết định |
|---|---|---|---|
| Checkpoint có sẵn | Dùng model sentiment tiếng Việt đã fine-tune | Có baseline nhanh, không có dữ liệu gán nhãn nội bộ | Bắt đầu ở giai đoạn benchmark |
| Fine-tune PhoBERT | Fine-tune `vinai/phobert-base-v2` hoặc checkpoint tương thích trên dữ liệu hội thoại | Cần phù hợp văn phong họp, thuật ngữ chuyên ngành, accent/STT noise | Hướng production khuyến nghị |
| Model tự xây nhẹ | TF-IDF + Logistic Regression/SVM hoặc PhoBERT embedding + classifier | Cần baseline dễ giải thích, CPU, so sánh | Bắt buộc làm baseline đối chứng |
| LLM | Phân tích chủ đề/tóm tắt, không dùng làm source-of-truth sentiment realtime | Cần giải thích giàu ngữ cảnh sau họp | Optional, hậu xử lý có evidence |

Không nên gọi LLM cho mỗi segment realtime: chậm, tốn GPU/chi phí, khó tái lập và nhãn dễ dao động. PhoBERT classifier là worker chuyên biệt; LLM (nếu có) chỉ nhận các aggregate đã lọc để tạo tóm tắt.

## 3. Kiến trúc đích

```text
                         PostgreSQL (application-owned)
                                      │
          transcript_segments finalized / revision event / meeting finalized
                                      │
                                      ▼
                 AI dispatcher (idempotent, debounce 15–30 giây)
                                      │
                           Redis Stream: ai.analysis.jobs
                                      │
                                      ▼
                        sentiment worker (GPU ưu tiên)
      quality gate → language router → unit builder → model inference
                                      │
                    transaction: predictions + aggregates + outbox event
                                      │
                         Redis Pub/Sub / SSE / WebSocket
                                      │
                                      ▼
                                  Dashboard Web UI
```

Các nguyên tắc vận hành:

- Chỉ job trên segment `is_final=true`, `retracted=false`; revision mới làm invalid prediction cũ.
- Job có khoá idempotency theo `meeting_id + kind + source_revision + model_version`.
- Worker tách process/container khỏi FastAPI để inference không chặn API.
- PostgreSQL là source of truth; Redis chỉ vận chuyển job/live fan-out.
- Mọi prediction phải lưu `model_version`, `preprocessing_version`, `source_segment_ids`, timestamps và xác suất lớp.
- Khi model hoặc tiền xử lý đổi, tạo run mới; không overwrite lịch sử.

## 4. Thiết kế dữ liệu bổ sung

Các bảng hiện có thiếu `analysis_runs` và `analysis_results` dù đã được nêu trong tài liệu định hướng. Migration tiếp theo nên bổ sung tối thiểu các bảng sau.

### 4.1 Bảng đề xuất

| Bảng | Trường quan trọng | Mục đích |
|---|---|---|
| `analysis_runs` | `id`, `meeting_id`, `kind`, `source_revision`, `model_version`, `status`, `started_at`, `finished_at`, `metrics` | Theo dõi một lần chạy, idempotency |
| `analysis_units` | `id`, `meeting_id`, `speaker_key`, `segment_ids JSONB`, `text`, `token_count`, `start_at/end_at`, `quality_status`, `quality_reasons`, `language` | Input đã chuẩn hoá, truy vết về transcript |
| `sentiment_predictions` | `id`, `analysis_unit_id`, `analysis_run_id`, `label`, `confidence`, `probabilities JSONB`, `polarity_score`, `inference_ms`, `is_current` | Kết quả model cấp unit |
| `meeting_sentiment_windows` | `meeting_id`, `window_start/end`, `scope`, `speaker_key nullable`, `positive_weight`, `neutral_weight`, `negative_weight`, `score`, `coverage` | Dữ liệu biểu đồ nhanh |
| `model_registry` | `model_version`, `task`, `base_model`, `labels`, `artifact_uri`, `checksum`, `thresholds`, `activated_at` | Reproducibility và rollback |
| `annotation_tasks` | `id`, `analysis_unit_id`, `assigned_to`, `status`, `gold_label`, `notes`, `adjudicated_at` | Human-in-the-loop/tạo tập dữ liệu |

Ràng buộc nên có:

```text
UNIQUE (meeting_id, kind, source_revision, model_version)      -- analysis_runs
UNIQUE (analysis_run_id, analysis_unit_id)                      -- predictions
INDEX  (meeting_id, start_at)                                   -- units và windows
INDEX  (meeting_id, speaker_key, window_start)                  -- dashboard theo speaker
```

`source_revision` có thể là revision tăng dần của toàn meeting hoặc hash ổn định của các `(segment_id, revision)` finalized. Với MVP, thêm `transcript_revision` trên `meetings`, tăng trong cùng transaction khi segment thay đổi; final run lấy snapshot revision này.

### 4.2 Chính sách invalidation

1. Segment draft không có prediction.
2. Segment bị retract hoặc sửa: prediction/unit liên quan chuyển `is_current=false`.
3. Dispatcher tạo unit và run mới từ `transcript_revision` mới.
4. Dashboard mặc định chỉ đọc `is_current=true` của model đang active.
5. Finalizer sau cuộc họp luôn enqueue một final run, dù live run đã từng chạy.

## 5. Quy trình xử lý dữ liệu

### 5.1 Quality gate (trước model)

| Kiểm tra | Quy tắc MVP | Hành động |
|---|---|---|
| Finality | `is_final=true`, không retracted | Bắt buộc |
| Độ dài | < 3 token hoặc chỉ ký tự lặp | bỏ/`unknown` |
| Trùng lặp | fingerprint text lặp gần nhau trong cùng speaker/window | đánh cờ hoặc gộp |
| Ngôn ngữ | nhận diện `vi`, `en`, `other`, `mixed` | route sang model tương ứng hoặc `unknown` |
| Nhiễu STT | tỉ lệ ký tự bất thường, câu vô nghĩa, zero duration | `review` hoặc loại |
| Nội dung không họp | heuristic/keyword hoặc classifier cho nhạc/quảng cáo | loại khỏi aggregate, vẫn giữ raw transcript |
| PII | phát hiện số điện thoại/email/ID khi logs/export | che trước log/annotation/export |

Không được “sửa” text raw trong `transcript_segments`. Lưu text đã chuẩn hoá ở `analysis_units`, cùng `preprocessing_version`; bảo toàn raw transcript để audit.

### 5.2 Chuẩn hoá tiếng Việt

1. Unicode NFC, chuẩn hoá khoảng trắng và punctuation nhẹ.
2. Giữ nguyên dấu tiếng Việt; không lower-case bắt buộc nếu tokenizer/checkpoint không yêu cầu.
3. Không xoá stopword hoặc stemming đối với PhoBERT.
4. Không dịch tự động tiếng Việt sang ngôn ngữ khác trước classifier.
5. Gộp context cùng speaker có giới hạn; không gộp qua speaker vì có thể đảo nghĩa/cảm xúc.
6. Cắt sequence theo giới hạn model (thường 256 token cho realtime); final analysis có thể sliding window + pooling.

### 5.3 Live và final analysis

| Chế độ | Trigger | Input | SLA mục tiêu | Mục đích |
|---|---|---|---|---|
| Live | 15–30 giây debounce sau finalized segment | delta units kể từ revision trước | < 10 giây sau debounce | xu hướng dashboard |
| Final | webhook finalization sau reconcile | toàn bộ transcript snapshot | < 2 phút với meeting thường | báo cáo chuẩn/chốt aggregate |
| Backfill | thay model hoặc sửa pipeline | meeting đã chọn/batch | async | so sánh model, không ảnh hưởng live |

## 6. Chiến lược dữ liệu và huấn luyện model

### 6.1 Chuẩn bị dữ liệu gán nhãn

Không lấy prediction của model làm gold label. Tạo tập dữ liệu từ transcript thực đã có consent, ẩn danh khi cần, sau đó gán nhãn ở cấp `analysis unit`.

1. Viết guideline nhãn với ví dụ hội thoại, sarcasm, câu hỏi trung tính, phủ định và code-switching.
2. Hai annotator độc lập gán nhãn mỗi unit; có nhãn `unclear/insufficient-context`.
3. Adjudication cho các điểm bất đồng; đo Cohen's kappa hoặc Krippendorff's alpha.
4. Split theo **meeting**, không split ngẫu nhiên theo segment, để tránh câu/giọng người nói bị rò sang test.
5. Cân bằng hoặc gán class weight vì nhãn neutral thường áp đảo.
6. Ghi nguồn dữ liệu, consent, phiên bản guideline và policy retention.

Mốc thực dụng đầu tiên: 1.000–2.000 unit đã adjudicate để benchmark; 3.000–10.000 unit đa miền để fine-tune có ý nghĩa. Chất lượng nhãn quan trọng hơn số lượng thô.

### 6.2 Baseline, fine-tuning, chọn model

Thứ tự thực nghiệm:

1. Baseline heuristic + `unknown` để kiểm tra data pipeline.
2. Baseline TF-IDF + Logistic Regression trên tập nội bộ.
3. Chạy checkpoint PhoBERT sentiment có sẵn trên cùng test set.
4. Fine-tune PhoBERT với hyperparameter/config được version hoá.
5. Chỉ promote model khi vượt baseline theo tiêu chí đã chốt và không làm xấu nhóm dữ liệu quan trọng.

Đánh giá bắt buộc: macro F1 (chính), precision/recall/F1 từng lớp, confusion matrix, coverage sau quality gate, calibration (ECE/Brier score), P95 inference latency và lỗi theo ngôn ngữ/độ dài/speaker/meeting domain. Không chỉ báo accuracy vì lệch lớp neutral có thể làm accuracy đẹp nhưng model không hữu ích.

Ngưỡng release gợi ý cho MVP nội bộ: macro F1 >= 0.70 trên test set holdout, F1 lớp negative không thấp hơn ngưỡng nhóm định trước, coverage >= 70% trên meeting tiếng Việt sạch, P95 batch inference phù hợp tài nguyên. Các số này là gate khởi đầu, phải được điều chỉnh sau baseline thật.

### 6.3 Model serving

- Artifact model nằm trong model registry/storage riêng, có checksum; không tải model tùy ý mỗi request.
- Worker load một lần lúc startup, expose health/readiness gồm `model_version`.
- Infer theo micro-batch để tận dụng GPU; giới hạn queue/backpressure.
- CPU fallback cho development, GPU cho production nếu latency/throughput yêu cầu.
- Canary một phần meeting hoặc chạy shadow mode trước khi đổi active model; so sánh prediction chứ không ghi đè.

## 7. API contract phục vụ dashboard

Giữ dashboard chỉ gọi backend; không lộ Vexa key, Redis hay model endpoint.

| Method | Endpoint | Mục đích |
|---|---|---|
| `GET` | `/v1/meetings/{id}/analytics/overview` | KPI, coverage, model/version, trạng thái analysis |
| `GET` | `/v1/meetings/{id}/analytics/timeline?window=60` | time series sentiment toàn meeting |
| `GET` | `/v1/meetings/{id}/analytics/speakers` | aggregate theo speaker, không xếp hạng con người |
| `GET` | `/v1/meetings/{id}/analytics/units` | danh sách evidence có filter label/speaker/time/confidence |
| `POST` | `/v1/meetings/{id}/analysis` | enqueue live/final/backfill theo quyền |
| `GET` | `/v1/meetings/{id}/analysis` | trạng thái runs và lỗi đã xử lý an toàn |
| `POST` | `/v1/analytics/feedback` | người dùng xác nhận/sửa nhãn, tạo annotation task |

Sự kiện live mới:

```json
{
  "type": "analysis.sentiment.updated",
  "meeting_id": "uuid",
  "data": {
    "source_revision": 42,
    "model_version": "phobert-sentiment-2026-09-01",
    "window_start": "2026-09-20T08:05:00Z",
    "score": -0.18,
    "coverage": 0.82
  }
}
```

Tuân theo cơ chế replay cursor/outbox hiện có. API phải kiểm tra owner/workspace membership trước mọi lần đọc, kể cả SSE/WebSocket và feedback.

## 8. Thiết kế dashboard

### 8.1 Dashboard meeting detail (MVP)

```text
┌──────────────── Meeting: 20/09/2026 · Analysis completed ────────────────┐
│ Positive 48%   Neutral 39%   Negative 13%   Coverage 82%   [Model v...] │
├───────────────────────────────────────────────────────────────────────────┤
│ Sentiment theo thời gian                                                   │
│  +1 ──╮  ╭───╮                                                            │
│   0 ──╰──╯   ╰──────╮                                                     │
│  -1 ─────────────────╰───╮────────────────────────────────────────       │
├───────────────────────┬───────────────────────────────────────────────────┤
│ Theo người nói        │ Evidence / Transcript                              │
│ A: +0.23  ███████     │ [08:05] Phuong Nguyen · negative · 0.78           │
│ B: -0.11  ████        │ "…"  [mở transcript tại timestamp]               │
│ Unknown: 18%          │ [08:07] ...                                       │
└───────────────────────┴───────────────────────────────────────────────────┘
```

Các thành phần cần có:

- KPI: tỷ lệ nhãn, sentiment score, coverage, số unit bị bỏ và model/version.
- Line/area chart theo cửa sổ thời gian, tooltip hiển thị sample size và confidence.
- Breakdown theo speaker chỉ trong phạm vi meeting; luôn thể hiện coverage, không tạo “điểm đánh giá nhân sự”.
- Evidence list: click một điểm biểu đồ mở các analysis unit, transcript nguồn, thời gian, nhãn/xác suất và lý do quality gate.
- Bộ lọc: thời gian, speaker, label, min confidence, chỉ hiện accepted/unknown.
- Trạng thái realtime: `waiting`, `processing`, `partial`, `completed`, `failed`; failure không làm trang trắng.
- Nút feedback “Đúng/Sai/Không đủ ngữ cảnh” có audit trail, không sửa prediction lịch sử.

### 8.2 Nguyên tắc UX và diễn giải

- Hiển thị “sắc thái của transcript”, không hiển thị “cảm xúc của con người” như một sự thật.
- Với confidence thấp hoặc coverage thấp, dùng màu trung tính và thông báo giới hạn dữ liệu.
- Biểu đồ phải có `n` unit/coverage để tránh hiểu sai từ mẫu nhỏ.
- `unknown` là kết quả hợp lệ, không gộp vào neutral.
- Không dùng màu đỏ làm cảnh báo con người; chỉ dùng cho polarity của nội dung và có tooltip giải thích.

## 9. Bảo mật, quyền riêng tư và retention

1. Chỉ phân tích meeting có thông báo/consent phù hợp chính sách tổ chức và pháp luật áp dụng.
2. Áp RBAC theo owner/workspace cho raw transcript, evidence, dashboard và export.
3. Mã hoá khi truyền (TLS) và at rest theo hạ tầng; secrets chỉ ở environment server-side.
4. Không ghi raw transcript, token, header hoặc PII vào application log/trace/model error.
5. Có policy retention riêng cho audio, raw transcript, prediction, annotation; cung cấp xoá theo meeting/user và xoá cascade jobs/artifacts liên quan.
6. Feedback/annotation có audit log (ai, lúc nào, thay đổi gì); giới hạn người được xem raw transcript.
7. Khi export dashboard, mặc định ẩn evidence text hoặc yêu cầu quyền cao hơn.

## 10. Kế hoạch triển khai step-by-step (chưa viết code)

### Phase A — Chốt product và nhãn

1. Chọn scope MVP: Vietnamese-first, 3 nhãn polarity + `unknown`.
2. Chốt ngưỡng đầu vào, definition `analysis unit`, window dashboard, retention và consent.
3. Viết annotation guideline và tiêu chí không đủ dữ liệu.
4. Chốt KPI: macro F1, coverage, latency, tỷ lệ feedback không đồng ý.

**Checkpoint:** tài liệu nhãn, policy, acceptance criteria được duyệt; chưa triển khai model.

### Phase B — Audit transcript và data contract

1. Dùng dữ liệu đã được phép để profile: ngôn ngữ, độ dài segment, duplicate, empty/zero duration, tỷ lệ noise và speaker key thiếu.
2. Xác định mapping timestamp: transcript mẫu đang có `start/end` epoch seconds và `absolute_start_time`; schema production nên giữ thêm absolute timestamp để vẽ đúng timeline.
3. Chốt JSON schema normalized của segment và analysis unit; viết test fixtures gồm tiếng Việt, code-switch, transcript lỗi, retract và revision.
4. Quyết định model routing: MVP PhoBERT chỉ nhận `vi`; non-vi/mixed đi `unknown` trước khi có model tương ứng.

**Checkpoint:** báo cáo data quality và contract test được chốt; không dùng raw sample để kết luận về chất lượng model.

### Phase C — Database, queue và lifecycle analysis

1. Tạo migration cho `analysis_runs`, `analysis_units`, `sentiment_predictions`, `meeting_sentiment_windows`, `model_registry`, `annotation_tasks`; bổ sung `transcript_revision` và absolute time cần thiết.
2. Thêm repository có transaction và idempotency; test revision/retract không để prediction cũ active.
3. Mở rộng outbox/Redis event cho `analysis.requested`, `analysis.status.changed`, `analysis.sentiment.updated`.
4. Tách worker container/process; thêm DLQ/retry có giới hạn, correlation ID và metrics queue.

**Checkpoint:** submit trùng job chỉ sinh một run; restart worker không mất job; finalizer tạo đúng một final analysis job.

### Phase D — Quality gate và baseline

1. Implement deterministic preprocessing/versioning và language route.
2. Implement unit builder, duplicate/noise rules; lưu lý do loại để dashboard giải thích coverage.
3. Chạy heuristic baseline, rồi TF-IDF + Logistic Regression làm comparator.
4. Tạo test unit cho phủ định, tiếng Việt có dấu, code-switch, câu cực ngắn, repeated text và PII redaction log.

**Checkpoint:** quality report tái lập được theo `preprocessing_version`, mọi unit có source segments, pipeline không phân tích draft/retracted segment.

### Phase E — PhoBERT benchmark và fine-tune

1. Đóng băng train/validation/test split theo meeting; ghi dataset manifest/version.
2. Benchmark checkpoint sentiment PhoBERT sẵn có và baseline trên exact cùng holdout set.
3. Fine-tune PhoBERT nếu baseline chưa đạt; lưu config, random seed, metrics, confusion matrix, artifact checksum.
4. Calibrate confidence và chọn threshold `unknown` bằng validation set, không dùng test set để tune.
5. Register candidate model; shadow-run trên meeting mới trước khi activate.

**Checkpoint:** model card, eval report và rollback plan; chỉ activate khi đạt quality/latency gate đã duyệt.

### Phase F — Serving, API và dashboard

1. Đóng gói inference worker, health/readiness, GPU/CPU config và bounded batch queue.
2. Implement live debounce, final full-run, backfill có quyền admin; add observability latency/error/coverage.
3. Implement analytics endpoints và SSE/WS event contract, kèm RBAC/owner test.
4. Xây dashboard meeting detail theo wireframe; link evidence đến transcript timestamp; thêm empty/loading/error states.
5. Thêm feedback capture và annotation review workflow.

**Checkpoint:** một meeting E2E hiển thị timeline + evidence đúng source, realtime update không lặp, user khác không truy cập được dữ liệu.

### Phase G — Production hardening

1. Load test số meeting/segment mục tiêu; chỉnh batch size, concurrency, Redis/DB indexes.
2. Thiết lập monitoring: job lag, queue depth, model error, P95 inference, analysis duration, coverage, unknown rate, API 5xx.
3. Alert khi job queue quá ngưỡng, model không ready, coverage giảm bất thường hoặc final run fail.
4. Kiểm thử retention/deletion, export authorization, backup/restore và model rollback.
5. Thiết lập canary deployment/model registry approval và runbook incident.

**Checkpoint:** SLO, dashboard vận hành, security review và rollback rehearsal pass.

## 11. Test plan và Definition of Done

| Nhóm | Điều kiện pass |
|---|---|
| Data correctness | mỗi prediction truy ngược được đến segment ID, revision, text-normalized version và model version |
| Idempotency | retry/restart/webhook lặp không tạo run/prediction/aggregate trùng |
| Quality gate | draft, retract, short/noise/non-Vietnamese được xử lý đúng policy; `unknown` không biến thành neutral |
| Model | test holdout theo meeting đạt gate; report đủ F1 mỗi lớp, calibration, latency và coverage |
| API/AuthZ | user không thuộc workspace nhận 404/403 với mọi analytics/evidence/stream endpoint |
| Dashboard | tooltip/evidence/timestamp khớp dữ liệu DB; low-confidence và low-coverage hiển thị rõ |
| Realtime | final segment đến dashboard sau debounce + inference theo SLA; reconnect không mất event cuối |
| Privacy | raw transcript/PII/secrets không có trong logs, client bundle hay metrics labels |
| Operations | worker down/retry/DLQ/rollback model có test/runbook |

Definition of Done cho phiên bản đầu: một cuộc họp tiếng Việt có transcript đủ sạch đi qua finalizer, tạo đúng một analysis run bằng model version xác định, dashboard hiển thị polarity timeline và breakdown theo speaker với coverage/confidence, mọi điểm đều mở được evidence transcript, và dữ liệu bị sửa/retract không còn xuất hiện trong aggregate hiện hành.

## 12. Thứ tự code được đề xuất sau khi duyệt tài liệu

1. Migration + repository + `transcript_revision`.
2. Analysis dispatcher/worker skeleton và idempotent lifecycle, chưa nạp model.
3. Quality gate + unit builder + fixtures/test.
4. Baseline inference và model registry.
5. PhoBERT benchmark/fine-tune + serving.
6. Analytics API/SSE events.
7. Dashboard + evidence/feedback.
8. Load test, security, monitoring, production rollout.

Không bắt đầu dashboard “đẹp” hoặc fine-tune PhoBERT trước khi data contract, quality gate và ground-truth annotation guideline đã chốt: ba phần này quyết định dashboard có đáng tin hay không.

## 13. Tài liệu triển khai kỹ thuật liên quan

Chi tiết contract pipeline, cấu trúc module dự kiến, lifecycle worker, API query/UI flow và Docker CPU/GPU được đặc tả tại [TRANSCRIPT_AI_DATA_ANALYSIS.md](TRANSCRIPT_AI_DATA_ANALYSIS.md). Tài liệu đó lấy trực tiếp `transcript.json` làm case study, đồng thời nêu rõ các nhãn cảm xúc ở case study chỉ là đánh giá minh hoạ và không thay thế output model hay dữ liệu gán nhãn.

Thứ tự hai tài liệu:

1. Đọc `TRANSCRIPT_AI_DATA_ANALYSIS.md` để chốt data contract và deploy/code design.
2. Dùng tài liệu này làm roadmap model quality, API/dashboard, kiểm thử và Definition of Done.
3. Chỉ sau các checkpoint đã duyệt mới tạo migration, worker, Docker services hoặc frontend code.
