# Tổng hợp cơ sở lý thuyết và triển khai hệ thống cho khóa luận

> Mục đích: tài liệu master để chỉnh sửa khóa luận LaTeX, chuẩn bị buổi xin góp ý giảng viên và phân biệt rõ phần **đã chứng minh bằng triển khai** với phần **cần thực nghiệm/nghiên cứu tiếp**.  
> Không dùng tài liệu này để tuyên bố một người có hoặc không có trầm cảm.

## 1. Định vị khoa học và phạm vi nên chốt

### 1.1 Vấn đề cốt lõi

Khóa luận hiện trộn ba bài toán khác nhau:

| Lớp bài toán | Câu hỏi trả lời | Dữ liệu/nhãn cần có | Trạng thái phù hợp hiện nay |
|---|---|---|---|
| Sentiment | Nội dung transcript biểu đạt tích cực/trung tính/tiêu cực thế nào? | Nhãn sentiment ở cấp đoạn hội thoại | MVP có thể triển khai và đánh giá |
| Emotion/intent | Nội dung có sắc thái như vui, bực bội, lo lắng hay yêu cầu hỗ trợ? | Multi-label emotion/intent, guideline rõ | Hướng nghiên cứu mở rộng |
| Depression screening | Người tham gia có dấu hiệu triệu chứng trầm cảm trong thời gian đánh giá không? | PHQ-9 tự báo cáo theo đúng cửa sổ thời gian + protocol lâm sàng/đạo đức | Không được suy ra từ một transcript họp ngắn; chỉ là hướng nghiên cứu tương lai |

**Khuyến nghị tên đề tài nộp hiện tại:**

> *Hệ thống phân tích sắc thái cảm xúc từ transcript tiếng Việt trong họp trực tuyến sử dụng PhoBERT và kiến trúc thời gian thực hướng bảo vệ quyền riêng tư.*

Nếu giữ cụm “sàng lọc dấu hiệu trầm cảm”, phải thu hẹp tuyên bố thành **nghiên cứu khả thi (feasibility study)** và bổ sung dữ liệu có PHQ-9 tự báo cáo, consent riêng, giám sát chuyên môn, protocol xử lý nguy cơ, cùng đánh giá validity. PHQ-9 là một công cụ tự báo cáo sàng lọc triệu chứng; nó không phải nhãn có thể trích xuất hợp lệ từ một câu nói hay một meeting đơn lẻ. [APA: PHQ assessment instruments](https://www.apa.org/depression-guideline/assessment), [Kroenke, Spitzer & Williams, 2001](https://pmc.ncbi.nlm.nih.gov/articles/PMC1495268/).

### 1.2 Luận điểm nghiên cứu có thể bảo vệ

1. Transcript tiếng Việt trong họp trực tuyến có nhiễu ASR, code-switching và đoạn ngắn; cần quality gate trước mô hình NLP.
2. PhoBERT là ứng viên hợp lý cho bài toán phân loại văn bản tiếng Việt, nhưng phải được benchmark công bằng với baseline trên cùng data split.
3. Kiến trúc event-driven, transcript versioning, worker tách API và evidence traceability là điều kiện để phân tích realtime có thể kiểm toán.
4. Dashboard phải mô tả **sắc thái của transcript**, confidence, coverage và evidence; không gán “điểm sức khỏe tâm thần” cho con người.
5. Quyền riêng tư, consent, human oversight và cơ chế xoá dữ liệu là yêu cầu thiết kế, không phải tính năng phụ.

WHO mô tả trầm cảm là trạng thái khí sắc trầm/mất hứng thú kéo dài, khác với biến đổi tâm trạng thường ngày; vì vậy sentiment của một đoạn nói không thể thay thế đánh giá bệnh lý. [WHO depression fact sheet](https://www.who.int/news-room/fact-sheets/detail/depression).

## 2. Mô hình khái niệm của hệ thống

```text
Âm thanh cuộc họp
  → Vexa/STT (Whisper hoặc provider tương đương)
  → transcript theo speaker và timestamp
  → backend application-owned (dedupe, revision, persistence)
  → quality gate + language router + analysis unit builder
  → sentiment classifier (baseline → PhoBERT sau benchmark)
  → aggregate có coverage/confidence/evidence
  → API/SSE → dashboard
```

### 2.1 Các khái niệm cần định nghĩa nhất quán trong Chương 1–3

| Khái niệm | Định nghĩa sử dụng trong khóa luận |
|---|---|
| Raw segment | Phân đoạn Vexa/STT chưa chỉnh sửa; dùng để audit, không xoá vì rule/model có thể chạy lại |
| Final segment | Segment đã hoàn tất từ nguồn; chỉ loại này được đưa inference |
| Analysis unit | 1–3 segment liền kề cùng speaker, giới hạn thời gian/token; là đơn vị dự đoán thay vì câu rất ngắn |
| Quality gate | Các rule xác định segment có đủ chất lượng để model phân tích; kết quả có `accepted`, `rejected`, lý do và language |
| Sentiment label | `positive`, `neutral`, `negative`; `unknown` là kết quả policy khi data/model không đủ, không gộp vào neutral |
| Confidence | Xác suất/độ chắc chắn của model sau calibration; không phải xác suất một người “có vấn đề tâm lý” |
| Coverage | Tỷ lệ analysis unit đủ điều kiện và có prediction; luôn hiển thị cùng aggregate |
| Evidence | Segment ID, revision, thời gian, normalized text, model/preprocessing version dùng để tạo prediction |

### 2.2 Công thức aggregate

Với một unit có xác suất lớp, score được xác định:

```text
polarity = P(positive) − P(negative) ∈ [-1, 1]
weight   = token_count × confidence
window_score = Σ(polarity × weight) / Σ(weight)
```

Chỉ unit `accepted`, confidence đạt threshold, `is_current=true` mới vào aggregate. Khi transcript bị sửa/retract hoặc model version thay đổi, result trước bị supersede chứ không overwrite lịch sử.

## 3. Cơ sở lý thuyết theo chương khóa luận

### Chương 1 — Bài toán, mục tiêu và câu hỏi nghiên cứu

- Nêu nhu cầu phân tích transcript tiếng Việt trong môi trường họp trực tuyến; tránh khẳng định có thể phát hiện bệnh.
- Mục tiêu tổng quát: xây dựng và đánh giá một hệ thống phân tích sentiment có evidence, privacy và realtime/near-realtime.
- Câu hỏi nghiên cứu đề xuất:
  1. Quality gate ảnh hưởng thế nào đến coverage và chất lượng sentiment trên transcript nhiễu?
  2. Baseline TF-IDF + Logistic Regression, PhoBERT và các baseline đa ngôn ngữ khác khác nhau thế nào trên cùng holdout set theo meeting?
  3. Kiến trúc event-driven có bảo toàn transcript/revision và đáp ứng SLA từ final segment đến dashboard không?
  4. Dashboard evidence/confidence có giúp người dùng hiểu đúng giới hạn model không?
- Giới hạn: chỉ Google Meet + Vexa trong thực nghiệm đã chạy; nền tảng khác là khả năng thiết kế, không phải claim triển khai.

### Chương 2 — Tổng quan và cơ sở lý thuyết

- Trình bày Transformer, self-attention, BERT và PhoBERT; giải thích tokenizer/checkpoint PhoBERT phải đi cùng nhau.
- Phân biệt sentiment, emotion, clinical screening/diagnosis bằng bảng ở mục 1.1.
- DSM-5/PHQ-9 chỉ nên đặt trong phần **bối cảnh và giới hạn**. Không vẽ bảng “ánh xạ trực tiếp DSM-5 → linguistic feature” như một phép chẩn đoán; thay bằng “giả thuyết nghiên cứu cần clinical validation”.
- Tổng quan ASR: WER/CER, diarization, VAD, acoustic echo, language identification và hallucination. Case `transcript.json` là evidence thực tế cho nhu cầu quality gate, không phải benchmark ASR.
- Tổng quan privacy/ethics: consent, data minimization, access control, auditability, human oversight. Không viết “tuân thủ GDPR/AI Act/pháp luật Việt Nam” nếu chưa có legal review/DPIA; dùng “được thiết kế để hỗ trợ các nguyên tắc…”. EU AI Act cần được tham chiếu trực tiếp từ văn bản pháp lý nếu được đề cập. [EUR-Lex Regulation (EU) 2024/1689](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689).

### Chương 3 — Dữ liệu và pipeline

#### 3.1 Data source và governance

Chia dữ liệu thành ba nguồn, không trộn lẫn vai trò:

| Nguồn | Mục đích | Được dùng train/test? | Điều kiện |
|---|---|---|---|
| Meeting transcript có consent | Đánh giá pipeline/domain adaptation | Có, nếu consent + de-identification + protocol duyệt | Không dùng phục vụ giám sát nhân sự/điểm cá nhân |
| Role-play kịch bản | Stress test ASR, code-switching, noise | Có thể dùng train dev nhưng phải ghi rõ synthetic | Không thay thế ground truth thực |
| Public social media | Pretrain/auxiliary data nếu license cho phép | Có điều kiện | Khác domain meeting; phải nêu domain shift |

Không dùng “augmentation” để tạo nhãn depression/PHQ-9. Với sentiment, augmentation phải chỉ áp dụng trên train, không được rò sang validation/test.

#### 3.2 Pipeline xử lý

1. Ingest Vexa REST/WS, upsert `(meeting_id, vexa_segment_id)` và tăng revision khi text/time/speaker đổi.
2. Chỉ lấy `is_final=true`, `retracted=false` vào worker.
3. Chuẩn hóa Unicode NFC/whitespace, giữ dấu tiếng Việt; không stem/loại stopword cho PhoBERT.
4. Quality gate: empty, short, invalid duration, duplicate, known hallucination, non-meeting content, language mismatch.
5. Language router: MVP chỉ `vi` vào PhoBERT; ngôn ngữ khác/mixed trả `unknown` cho đến khi có model đã đánh giá.
6. Build analysis unit theo cùng speaker và bounded context.
7. Infer, persist probability/model version/inference latency, aggregate 60 giây và phát outbox event.

#### 3.3 Độ trễ đúng cách

Không so sánh trực tiếp target end-to-end `<2s` với audio window 30 giây. Báo cáo tách:

```text
T_capture: âm thanh phát sinh → ASR tạo final segment
T_analysis: final segment event → dashboard update
T_e2e: T_capture + T_analysis
```

Với REST polling hiện tại, claim phù hợp là **near-realtime**; đo P50/P95 của `T_analysis`. Target `<2s` chỉ có thể áp dụng cho `T_analysis` hoặc khi dùng streaming ASR/partial transcript đã được kiểm chứng.

### Chương 4 — Mô hình và protocol thí nghiệm

#### 4.1 Baseline và candidate

| Nhóm | Vai trò |
|---|---|
| Rule baseline | Test data contract/quality gate; không dùng làm kết quả học thuật về ML |
| TF-IDF + Logistic Regression | Baseline có thể tái lập, CPU-friendly |
| TF-IDF + SVM | Comparator tuyến tính/non-linear rõ ràng |
| PhoBERT fine-tune | Candidate chính tiếng Việt |
| mBERT/XLM-R | Comparator đa ngôn ngữ nếu tài nguyên và dataset đủ |
| ViHealthBERT | Chỉ đưa vào nếu task/dataset/model card phù hợp và license rõ ràng; không giả định phù hợp meeting sentiment |

#### 4.2 Split, nhãn và metric

1. Annotation guideline nêu định nghĩa lớp, sarcasm, phủ định, code-switch, insufficient context.
2. Ít nhất hai annotator độc lập; adjudication; báo cáo agreement (Cohen’s kappa/Krippendorff’s alpha).
3. Split theo **meeting**, không split segment ngẫu nhiên, để tránh leakage speaker/ngữ cảnh.
4. Khóa test set trước tuning; chọn threshold trên validation.
5. Báo cáo macro-F1, precision/recall/F1 từng lớp, confusion matrix, calibration, coverage, P50/P95 inference. Accuracy đơn lẻ không đủ khi neutral mất cân bằng.
6. Bootstrap CI chỉ báo cáo khi đã chạy thật, ghi rõ số resample, seed và unit resample.

Không điền fabricated F1/AUC/Recall vào Chương 8. Nếu chưa fine-tune, đổi bảng “Kết quả” thành “Kế hoạch đánh giá”, hoặc đánh dấu chưa thực hiện trong draft gửi giảng viên.

### Chương 5 — Backend và kiến trúc realtime

```text
Vexa → FastAPI backend → PostgreSQL (source of truth)
                         └→ outbox → Valkey Stream → sentiment worker
                                                   └→ aggregates/outbox → SSE → dashboard
```

Các quyết định kỹ thuật:

- Backend không để browser gọi Vexa và không lộ Vexa API key.
- PostgreSQL lưu meetings, transcript segments, analysis runs, units, predictions, windows và outbox.
- Valkey/Redis chỉ dùng queue/fan-out; không là source of truth.
- Worker tách FastAPI để model inference không chặn REST/SSE.
- Idempotency key: `(meeting_id, kind, source_revision, model_version)`.
- Reconcile REST là fallback; WebSocket Vexa là phase kế tiếp sau khi source contract được kiểm chứng.

### Chương 6 — Dashboard và trải nghiệm người dùng

Dashboard hiện có thể trình bày dưới dạng **MVP implemented**:

- nhập application meeting UUID;
- KPI positive/neutral/negative, coverage, polarity và model version;
- timeline theo cửa sổ thời gian;
- evidence: speaker, transcript, timestamp, quality reason, label/confidence;
- SSE refresh khi `analysis.sentiment.updated`.

Không dùng traffic-light “rủi ro participant”, HR scoring, auto-notification hay “liên hệ hỗ trợ” như tính năng đã thực hiện. Đây chỉ là ý tưởng tương lai đòi hỏi consent, policy và đánh giá human-factors riêng.

### Chương 7 — Hạ tầng và DevOps

#### Đã triển khai local Compose

```text
backend:8088     FastAPI REST/SSE
worker           analysis queue consumer
postgres         persistent application data
redis/valkey     Stream/PubSub
dashboard:3000   Nginx static UI + /api reverse proxy
vexa network     external Docker network tới gateway
```

- `compose.yaml`: topology CPU local.
- `compose.gpu.yaml`: override lý thuyết cho worker GPU, không phải benchmark GPU đã báo cáo.
- Health check PostgreSQL/Valkey; backend health endpoint; worker recovery queued run.

Kubernetes, TimescaleDB, CI/CD, multi-region, HA và 20 concurrent sessions là **target architecture**. Giữ chúng trong mục “đề xuất production” trừ khi có manifest, deployment log và load-test thật.

### Chương 8 — Kết quả và đánh giá

#### 8.1 Bằng chứng đã có

| Hạng mục | Kết quả local đã kiểm chứng ngày 2026-09-20 |
|---|---|
| Backend transcript persistence | 13 segment, 12 finalized |
| Final analysis run | `succeeded` |
| Analysis unit | 6 |
| Unit accepted | 4 |
| Coverage | 66.7% |
| Runtime model | `baseline-rules-v1` |
| Dashboard | KPI, timeline, evidence, SSE hoạt động |

Các số này chỉ chứng minh **pipeline integration**, không chứng minh quality sentiment/PhoBERT, ASR WER hay depression screening.

#### 8.2 Bảng thí nghiệm cần hoàn thiện

- Model: dataset manifest, n train/val/test theo meeting, class distribution, kappa, F1/recall/macro-F1, calibration, CI.
- ASR: audio ground truth, WER/CER theo tiếng Việt, noise/echo/song/code-switching.
- System: `T_capture`, `T_analysis`, `T_e2e`, throughput, queue lag, API error rate, resource profile.
- UX: protocol người dùng, task completion, SUS/NASA-TLX nếu có, n participant và limitations.

### Chương 9 — Privacy, ethics và an toàn

1. Consent cụ thể cho transcript analysis; không dùng consent họp chung như consent nghiên cứu y tế.
2. Mục đích giới hạn: không employment/education ranking, kỷ luật hay quyết định tự động.
3. Data minimization: không audio/video thô nếu không cần; raw transcript và evidence cần retention/deletion policy.
4. AuthZ theo owner/workspace, TLS khi triển khai, không log secret/raw transcript; audit feedback/access.
5. `unknown` và low coverage là output hợp lệ; không ép hệ thống trả cảnh báo.
6. Nếu nghiên cứu tới self-harm/suicidality: dừng trước khi có IRB/ethics approval, clinical supervisor và crisis-response protocol. Không dùng keyword alert như can thiệp tự động.

### Chương 10 — Kết luận

Kết luận phù hợp bằng chứng hiện tại:

> Khóa luận đã xây dựng và kiểm chứng một MVP end-to-end cho ingest transcript, quality gate, analysis lifecycle, persistence, realtime delivery và evidence dashboard. PhoBERT fine-tune, benchmark đa mô hình và validation trên dữ liệu được gán nhãn là công việc tiếp theo, không phải kết quả đã đạt.

Không viết “đã công bố pipeline”, “đã đạt p95 X ms”, “tích hợp Meet/Zoom/Teams/Jitsi”, “tuân thủ pháp luật”, hoặc “cải thiện AUC 0.03–0.08” nếu không có bằng chứng thực nghiệm/pháp lý tương ứng.

## 4. Mapping thiết kế sang source code hiện có

| Chức năng | Source code |
|---|---|
| Vexa ingest/reconcile | `source/meeting-intelligence-backend/app/vexa.py`, `app/service.py` |
| API/SSE/webhook | `app/main.py` |
| Analysis contracts, quality, units | `app/analysis/` |
| Persistence/idempotency/aggregate | `app/repositories/analysis.py`, `app/models.py` |
| Worker/Valkey stream | `app/workers/sentiment.py`, `app/queue.py` |
| Analytics endpoints | `app/api/analytics.py` |
| Dashboard | `dashboard/index.html`, `dashboard/app.js`, `dashboard/styles.css` |
| Local deployment | `compose.yaml`, `compose.gpu.yaml`, `Dockerfile` |
| Verification | `tests/test_quality.py`, `tests/test_units.py` |

## 5. Kế hoạch chỉnh LaTeX trước khi gửi giảng viên

1. **Bật bibliography:** bỏ comment ở `main.tex` dòng 288–289, chạy BibTeX/Biber theo engine đã chọn, sửa toàn bộ citation unresolved. Không sửa citation bằng tay trong PDF.
2. **Đổi status chương:** “Kết quả thực nghiệm” thành “Thiết kế đánh giá và kết quả integration MVP” cho đến khi có benchmark thật.
3. **Lọc claim:** dùng ba tag khi rà soát mọi chương: `[ĐÃ TRIỂN KHAI]`, `[ĐỀ XUẤT]`, `[CẦN ĐÁNH GIÁ]`. Bản nộp bỏ tag, nhưng giữ đúng modal verb: “đã”, “đề xuất”, “sẽ đánh giá”.
4. **Thay placeholder:** 17 hình phải là screenshot/diagram do tác giả tạo hoặc hình có bản quyền/citation rõ; 115 `[CẦN ĐIỀN]` phải thành số liệu thật hoặc chuyển sang future-work.
5. **Sửa Chương 2 và 9:** PHQ-9/DSM-5 là background, không làm nhãn inferred; bỏ tuyên bố regulatory compliance chưa audit.
6. **Sửa Chương 6:** screenshot dashboard hiện tại, bỏ các screen/chức năng chưa code hoặc gắn “thiết kế đề xuất”.
7. **Sửa Chương 7:** đưa Compose hiện tại làm implementation; K8s/Timescale/cloud thành production roadmap.
8. **Rà layout PDF:** thay `minted` bằng `listings` nếu build environment không bật `-shell-escape`; sửa bảng tràn bằng `tabularx/longtable`, tăng `\headheight` theo cảnh báo `fancyhdr`.

## 6. Checklist buổi xin góp ý giảng viên

Đề nghị giảng viên quyết định cùng sinh viên bốn điểm trước khi đầu tư fine-tune:

1. Phạm vi chính thức: sentiment transcript hay feasibility depression screening có protocol lâm sàng?
2. Nguồn data, consent, retention, annotation guideline và người adjudicate.
3. Mô hình đánh giá: task/label/split/metric/deployment gate nào là bắt buộc.
4. Mức claim triển khai được phép: Google Meet + Vexa local MVP; không mở rộng sang nền tảng/hạ tầng chưa benchmark.

Thông điệp đề xuất:

> Em đã hoàn thành khung nghiên cứu và MVP end-to-end cho transcript analysis có evidence. Em mong thầy/cô góp ý về phạm vi bài toán, tính hợp lệ của dữ liệu/nhãn và protocol đánh giá trước khi em hoàn thiện benchmark PhoBERT và phần thực nghiệm.

## 7. Thứ tự triển khai nghiên cứu tiếp theo

1. Chốt scope sentiment-first và ethics/data governance.
2. Versioned database migration (Alembic) và retention/delete workflow.
3. Annotation pilot, double annotation, adjudication và dataset manifest.
4. TF-IDF/LR baseline → PhoBERT benchmark → evaluation report tái lập.
5. PhoBERT serving adapter, model registry, calibration và shadow run.
6. Đo ASR/system/UX theo protocol trước; đưa số liệu/hình thực vào Chương 8.
7. Rà claim, citation, legal/ethical review và render PDF trước khi nộp.
