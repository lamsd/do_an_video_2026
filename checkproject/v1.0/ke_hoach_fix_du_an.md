# Kế hoạch sửa dự án và luận văn theo phản biện

## 0. Quy ước và quyết định phạm vi

- `[DOC]`: chỉ sửa luận văn/tài liệu, không tạo số liệu mới.
- `[CODE]`: sửa mã nguồn hoặc test.
- `[TN]`: **phải chạy thực nghiệm/kiểm chứng thật**. Không điền số liệu ước lượng.
- `[CONSENT]`: chỉ làm với transcript/cuộc họp thật khi có sự đồng ý rõ ràng của người tham gia; không đưa dữ liệu thật, secret hay log nhạy cảm vào Git.

### Hướng khuyến nghị: giữ MVP kiến trúc, không tuyên bố đã có model ML

Tên đề tài/phạm vi nên dùng:

> **Thiết kế và kiểm chứng kiến trúc hệ thống xử lý transcript họp trực tuyến có khả năng tích hợp mô hình phân tích sentiment tiếng Việt.**

Lý do: mã hiện tại chỉ có `baseline-rules-v2`, là rule-based baseline. Nó phù hợp để kiểm chứng pipeline, nhưng chưa đủ bằng chứng để tuyên bố PhoBERT/custom ML hoặc chất lượng sentiment định lượng.

Chỉ chọn hướng ML đầy đủ ở Mục 8 nếu còn đủ thời gian và có corpus đúng miền được gán nhãn.

---

## 1. Definition of Done trước khi in/bảo vệ

- [ ] Không còn placeholder `[CẦN ĐIỀN: ...]` trên bìa, cam đoan, cảm ơn.
- [ ] Tóm tắt và Abstract cùng cấu trúc và cùng claim.
- [ ] Tiêu đề, mục tiêu, đóng góp và kết luận đều mô tả đúng MVP kiến trúc.
- [ ] Chương 8 không còn bảng kết quả trống.
- [ ] Có evidence bundle thật cho unit test, integration smoke, runtime reachability và test thay adapter.
- [ ] Có bảng kết quả kiểm chứng hệ thống với số lần chạy, pass/fail, latency P50/P95 và môi trường chạy.
- [ ] Coverage được tách thành `acceptance_rate`, `prediction_coverage`, `effective_coverage`.
- [ ] Không dùng confidence chưa calibrated làm trọng số của aggregate, hoặc ghi rõ đây chỉ là heuristic và có kiểm tra sensitivity.
- [ ] Chương 10 trả lời từng RQ bằng mức bằng chứng thực tế: Supported / Partially supported / Design-only.
- [ ] Notebook phân loại trầm cảm được tách khỏi phạm vi build/repo MVP hoặc có README cảnh báo rõ là ngoài phạm vi.

---

## 2. Sprint P0 — chặn lỗi phản biện nghiêm trọng

### Task P0-01 — Chốt scope và sửa claim

**Loại:** `[DOC]`  
**Tệp chính:** `01_introduction.tex`, `00_abstract.tex`, `04_model_selection.tex`, `08_experiments.tex`, `10_conclusion.tex`, `README.md`.

**Step by step**

1. Đổi tiêu đề theo hướng kiến trúc có kiểm chứng, hoặc giữ tiêu đề cũ nhưng bổ sung cụm “MVP/khả năng tích hợp model” trong Mục tiêu và Đóng góp.
2. Đổi `\section{Đóng góp dự kiến}` ở Chương 1 thành `\section{Đóng góp của khóa luận}`.
3. Thay mọi câu khẳng định model đã “phân tích đúng/đã kiểm chứng” bằng claim đúng mức: `baseline-rules-v2` chỉ kiểm chứng data contract và pipeline.
4. Giữ PhoBERT/MLflow/canary/Kubernetes ở phần “hướng phát triển” nếu chưa triển khai.
5. Đồng bộ Tóm tắt và Abstract: cả hai phải có Mục tiêu, Phương pháp, Kết quả thực tế, Giới hạn/Kết luận.

**Tiêu chí hoàn thành:** không còn mô tả PhoBERT là model runtime; Abstract không nói “để điền sau”.

### Task P0-02 — Hoàn tất hình thức và dọn bảng trống

**Loại:** `[DOC]`  
**Tệp chính:** `00_cover.tex`, `00_declaration.tex`, `00_abstract.tex`, `08_experiments.tex`, `main.tex`.

**Step by step**

1. Điền họ tên, MSSV, lớp, tháng/năm ở bìa và lời cam đoan.
2. Thêm danh mục hình theo mẫu LaTex của trường.
3. Không để Bảng 8.2/8.3 là mẫu trống trong chương kết quả:
   - nếu đã chạy: thay bằng kết quả thật theo Task P0-03 đến P0-06;
   - nếu chưa chạy: chuyển sang Phụ lục “Protocol thực nghiệm đề xuất”, không để ở Chương 8.
4. Chạy tìm placeholder trước khi build: `rg -n '\\[CẦN ĐIỀN|chưa đo|để điền sau|sẽ điền' Reports/thesis_latex_overleaf`.
5. Biên dịch PDF và kiểm tra mục lục/danh mục hình/bảng không lỗi tham chiếu.

**Tiêu chí hoàn thành:** PDF final không có placeholder hay ô kết quả rỗng.

### Task P0-03 — Tạo evidence bundle chuẩn cho mọi lần chạy

**Loại:** `[CODE] [TN]`  
**Đầu ra cần tạo:** `source/evidence/<EVID-ID>/` (không commit dữ liệu thật hoặc secret).

**Step by step**

1. Tạo cấu trúc mỗi evidence bundle:

   ```text
   source/evidence/EVID-YYYYMMDD-XXX/
   ├── manifest.md
   ├── commands.txt
   ├── stdout.log
   ├── environment.txt
   └── api-result.redacted.json   # chỉ khi có fixture tổng hợp
   ```

2. `manifest.md` phải ghi: Evidence ID, thời gian, người chạy, commit (`git rev-parse HEAD`), OS/CPU/RAM, Docker/Compose/Python version, image digest nếu có, dữ liệu synthetic/real, consent, kết quả và giới hạn.
3. `commands.txt` ghi nguyên lệnh chạy; `stdout.log` ghi output và exit code.
4. Không ghi `settings.env`, API key, header bí mật, transcript thật hay định danh người tham gia.
5. Trong Chương 8, chỉ dùng cụm “đã kiểm chứng” khi trỏ đến một `EVID-*` có bundle tương ứng.

**Nội dung để ghi vào luận văn:** thêm bảng evidence ở Mục 8.6, gồm `Evidence ID | Test | Commit | Environment | Kết quả | Artifact`.

---

## 3. Các thực nghiệm kiểm chứng hệ thống bắt buộc

### Task P0-04 — Unit và contract test

**Loại:** `[TN]`  
**Mục tiêu:** chứng minh các invariant code, không phải accuracy sentiment.

**Step by step**

1. Khởi động môi trường backend theo README.
2. Chạy test trong dependency lock:

   ```bash
   cd source/src/backend
   uv run pytest -q
   ```

3. Lưu output vào `EVID-UT-001/stdout.log`, cùng commit và phiên bản môi trường.
4. Nếu fail, sửa đúng test/code rồi chạy lại với Evidence ID mới; không sửa log cũ.
5. Cập nhật số lượng test từ output thực tế, không dùng con số “11 test” nếu suite đã thay đổi.

**Ghi vào Chương 8:**

| Evidence ID | Phạm vi | Lần chạy | Kết quả | Ý nghĩa | Không chứng minh |
|---|---|---:|---|---|---|
| EVID-UT-001 | quality, unit builder, service, Vexa parser | `<N>` | `<N>/<N> PASS` | invariant normalize/reject/dedup/parser | chất lượng ASR hay Macro-F1 sentiment |

**Câu kết luận được phép viết:** “Test đơn vị xác nhận các invariant đã định nghĩa của quality gate, unit builder và helper contract trong môi trường ghi nhận.”

### Task P0-05 — Smoke integration pipeline với fixture tổng hợp

**Loại:** `[TN]`  
**Mục tiêu:** xác nhận đường đi `API → PostgreSQL → Valkey → worker → analytics API`.

**Step by step**

1. Tạo `source/settings.env` cục bộ theo `settings.env.example`; không commit file này.
2. Khởi động service:

   ```bash
   cd source
   docker compose --env-file settings.env up -d --build
   ./scripts/verify.sh
   ./scripts/smoke-analysis-pipeline.sh
   ```

3. Chạy tối thiểu 10 lần độc lập. Mỗi run sinh UUID fixture riêng và script tự cleanup.
4. Với mỗi run, lưu timestamp, exit code, status `succeeded/failed`, tổng thời gian script, số unit, `model_version`, `preprocessing_version` và JSON API đã redaction.
5. Tính `success_rate = số run succeeded / tổng run`; chỉ báo cáo tỷ lệ này cho fixture tổng hợp.

**Ghi vào Chương 8:**

| Test | Fixture | Số run | Succeeded | Failed | Success rate | Model version | Kết luận đúng mức |
|---|---|---:|---:|---:|---:|---|---|
| Pipeline smoke | 2 segment tiếng Việt tổng hợp | `<R>` | `<S>` | `<F>` | `<S/R>` | `baseline-rules-v2` | Luồng nội bộ hoạt động với fixture; không là F1/accuracy |

**Không được ghi:** “Hệ thống đạt accuracy 100%” hoặc “model sentiment được đánh giá tốt”, vì fixture chủ động khớp marker rule.

### Task P0-06 — Đo latency và sửa định nghĩa coverage

**Loại:** `[CODE] [TN]`  
**Mục tiêu:** thay claim “near-real-time” bằng số đo có điều kiện rõ ràng.

**Step by step**

1. Bổ sung script benchmark dùng **fixture tổng hợp**, ví dụ 30 run, với 3 cỡ đầu vào: 2, 10, 30 segments; ghi `t_request`, `t_succeeded`.
2. Tính `T_pipeline = t_succeeded - t_request`; báo P50/P95/P99 theo từng cỡ input. Không gọi đây là `T_e2e` vì không gồm Vexa/ASR.
3. Ghi rõ: concurrency, warm-up, phần cứng, image digest, giới hạn CPU/RAM container và thời gian chạy.
4. Sửa backend/dashboard để trả và hiển thị ba metric:

   \[
   acceptance\_rate=A/T,\quad prediction\_coverage=P/A,\quad effective\_coverage=P/T
   \]

   Trong đó `T` là toàn bộ unit/segment được xem xét trước quality gate, `A` là accepted unit và `P` là unit có prediction khác `unknown`.
5. Thêm unit test cho các mẫu biên: `A=0`, `P=0`, nhiều unit bị reject, tất cả unit được predict.

**Ghi vào Chương 8:**

| Workload synthetic | Runs | P50 pipeline (ms) | P95 pipeline (ms) | P99 pipeline (ms) | Success rate | Điều kiện đo |
|---|---:|---:|---:|---:|---:|---|
| 2 segments | `<R>` | `<...>` | `<...>` | `<...>` | `<...>` | `<CPU/RAM/image/concurrency>` |
| 10 segments | `<R>` | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` |
| 30 segments | `<R>` | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` |

**Câu kết luận được phép viết:** “Trong workload fixture tổng hợp và cấu hình đã nêu, pipeline nội bộ có P95 là `<x>` ms; kết quả không bao gồm capture/ASR/Vexa và không phải SLO production.”

### Task P1-01 — Kiểm chứng thay classifier adapter (trả lời RQ2)

**Loại:** `[CODE] [TN]`  
**Mục tiêu:** chứng minh RQ2 bằng một adapter thứ hai, chưa cần PhoBERT.

**Cách làm ưu tiên:** thêm `DummyClassifierAdapter` quyết định cố định theo fixture, hoặc `TFIDFLogisticRegressionAdapter` nếu có artifact versioned. `Dummy` đủ để kiểm chứng boundary kiến trúc; TF-IDF+LR mạnh hơn nhưng phải có dataset huấn luyện hợp lệ.

**Step by step**

1. Đưa classifier được chọn vào config/factory; không sửa API, schema database hay JavaScript dashboard.
2. Đảm bảo adapter trả `Prediction` đủ label, confidence, probabilities, polarity, latency và `model_version` riêng.
3. Viết contract tests dùng **cùng fixture** cho `baseline-rules-v2` và adapter B.
4. Chạy integration hai lần, mỗi lần chỉ thay `MODEL_VERSION`/adapter config.
5. So sánh evidence: endpoint/DB schema/dashboard không đổi; `model_version` được lưu khác nhau và evidence trace đúng revision/model.

**Ghi vào Chương 8:**

| Adapter | API thay đổi | Schema thay đổi | Dashboard thay đổi | `model_version` evidence | Kết quả integration |
|---|---|---|---|---|---|
| RuleBaselineClassifier | Không | Không | Không | `baseline-rules-v2` | `<PASS/FAIL>` |
| `<Adapter B>` | Không | Không | Không | `<version>` | `<PASS/FAIL>` |

**Trả lời RQ2:** “Supported trong phạm vi hai adapter đã kiểm chứng”; không nói “đã chứng minh PhoBERT” nếu adapter B không phải PhoBERT.

### Task P1-02 — Fault/recovery và webhook idempotency

**Loại:** `[CODE] [TN]`  
**Mục tiêu:** biến mô tả outbox/idempotency thành bằng chứng.

**Step by step**

1. Viết integration tests cho webhook event trùng, chữ ký sai, timestamp hết hạn và revision đến muộn.
2. Chạy kịch bản worker restart trong khi job đang chờ/xử lý; kiểm tra run cuối cùng không duplicate prediction sai revision.
3. Chạy Valkey restart ngắn; ghi retry/reclaim, final status và thời gian recovery.
4. Không cần dùng Vexa/meeting thật cho nhóm test này; dùng fixture synthetic và database isolated.
5. Báo cáo failure có kiểm soát thay vì chỉ báo pass.

**Ghi vào Chương 8:**

| Evidence ID | Fault injected | Expected invariant | Observed result | Recovery time | Giới hạn |
|---|---|---|---|---:|---|
| `<EVID-REC-001>` | duplicate event | không tạo duplicate run | `<result>` | `<ms/s>` | fixture nội bộ |
| `<EVID-REC-002>` | worker restart | job được reclaim/idempotent | `<result>` | `<ms/s>` | không phải load test |
| `<EVID-REC-003>` | Valkey unavailable | retry/failure minh bạch | `<result>` | `<ms/s>` | `<...>` |

---

## 4. Các sửa kỹ thuật và luận văn đi kèm

### Task P0-07 — Sửa aggregate score/confidence

**Loại:** `[CODE] [DOC]`  
**Vấn đề:** confidence của `baseline-rules-v2` không calibrated nhưng công thức hiện nhân confidence và token count làm trọng số polarity.

**Step by step**

1. Phương án an toàn nhất: với baseline, aggregate bằng **đếm nhãn** và để polarity score là `null` hoặc ghi “heuristic”.
2. Nếu vẫn giữ weighted score, hiển thị cả unweighted và weighted score, giải thích mục đích visualization, không gọi là metric khoa học.
3. Chỉ cho confidence tham gia aggregate sau khi model có calibration evaluation trên validation/test độc lập.
4. Sửa công thức và wording ở `02_literature_review.tex`, `03_data_pipeline.tex`, `06_frontend.tex`, API/dashboard tương ứng.
5. Thêm test kiểm tra unit dài không tự tạo ảnh hưởng lớn chỉ do số token.

**Tiêu chí hoàn thành:** không có claim confidence là probability hay polarity aggregate là kết luận đáng tin cậy khi đang dùng rule baseline.

### Task P0-08 — Chương 2: Related work và research gap

**Loại:** `[DOC] [TN: nghiên cứu tài liệu]`  
**Lưu ý:** đây là thực nghiệm tài liệu, không phải chạy code. Chỉ thêm công trình đã đọc và trích dẫn được.

**Step by step**

1. Tách Chương 2 thành `Background`, `Related work`, `Research gap`.
2. Lập bảng tối thiểu 6–10 công trình: domain, language, input clean/ASR, model, dataset, metric, hạn chế liên quan.
3. Tìm các nhóm: Vietnamese sentiment; conversational/meeting sentiment; ASR noise downstream; meeting intelligence; provenance/auditability.
4. Viết 1 đoạn gap có dẫn chứng, không khẳng định “chưa ai làm” nếu không có systematic review.
5. Map gap trực tiếp đến contribution revision-aware provenance, adapter boundary và evidence-aware UI.

**Bảng để ghi:** `Công trình | Domain/ngôn ngữ | Input | Model | Evaluation | Hạn chế được luận văn xử lý`.

### Task P0-09 — DSR methodology và trả lời RQ

**Loại:** `[DOC]`.

**Step by step**

1. Thêm bảng DSR: Problem → Objectives → Artefact → Implementation → Demonstration → Evaluation → Communication.
2. Map mỗi bước tới chương, Evidence ID hoặc artifact thực tế.
3. Thêm subsection “Trả lời câu hỏi nghiên cứu” ở Chương 10.
4. Dùng trạng thái trung thực:
   - RQ1: Supported sau test data/revision/quality/pipeline.
   - RQ2: Supported chỉ sau Task P1-01; nếu chưa làm là Design-only.
   - RQ3: Partially supported với smoke nội bộ; Vexa E2E chỉ claim sau Task P2-01.
   - RQ4: Design-only trừ khi có user study.

### Task P1-03 — Chuẩn hóa thuật ngữ và giảm roadmap chưa hiện thực

**Loại:** `[DOC]`.

**Step by step**

1. Lần đầu dùng ghi song ngữ: “đơn vị phân tích (analysis unit)”; các lần sau ưu tiên tiếng Việt.
2. Chuẩn hóa: evidence → bằng chứng truy vết; quality gate → bộ kiểm tra chất lượng; runtime → môi trường thực thi; coverage → độ bao phủ dự đoán.
3. Chuyển phần Kubernetes/HA/multi-region/MLflow canary chưa chạy sang Future Work/Appendix.
4. Giữ mô tả kỹ thuật trực tiếp hỗ trợ reproducibility của các thực nghiệm đã làm.

### Task P1-04 — Tách notebook trầm cảm khỏi MVP

**Loại:** `[CODE] [DOC]`.

**Step by step**

1. Tìm mọi notebook/file/README liên quan depression/PHQ-9 trong source tree.
2. Di chuyển sang thư mục archive ngoài build/deploy MVP, hoặc gắn `README` nêu: ngoài phạm vi, không được chạy/deploy, không dùng kết quả cho sentiment.
3. Bảo đảm `compose.yaml`, test, README build và phụ lục không dẫn đến notebook đó như model runtime.
4. Nêu rõ trong Chương 1/9 rằng không suy luận mental health.

---

## 5. Cấu trúc Chương 8 sau khi sửa

1. **8.1 Câu hỏi đánh giá và phạm vi claim** — phân biệt system verification với model evaluation.
2. **8.2 Môi trường thực nghiệm** — commit/image, OS, CPU/RAM, Docker, config redaction.
3. **8.3 Dữ liệu/fixture** — synthetic fixture; nêu rõ không đại diện meeting thật.
4. **8.4 Kết quả unit/contract** — Task P0-04.
5. **8.5 Kết quả integration, adapter swap, recovery** — Task P0-05, P1-01, P1-02.
6. **8.6 Hiệu năng pipeline nội bộ** — Task P0-06; không gọi là ASR/Vexa E2E.
7. **8.7 Evidence bundle và reproducibility** — bảng EVID-ID.
8. **8.8 Threats to validity** — fixture synthetic, baseline rule, no real corpus, no user study, local hardware.
9. **8.9 Protocol tương lai** — model/ASR/UX chỉ giữ lại khi chưa thực hiện; chuyển bảng template vào đây hoặc Phụ lục.

---

## 6. Thực nghiệm chỉ làm khi có điều kiện phù hợp

### Task P2-01 — Vexa/Google Meet E2E thật

**Loại:** `[TN] [CONSENT]`.

**Chỉ làm khi:** có consent, endpoint webhook HTTPS, Vexa self-host hoạt động và quy trình xóa dữ liệu sau test.

**Step by step**

1. Chuẩn bị kịch bản ngắn, nội dung không nhạy cảm; participant đồng ý bằng văn bản.
2. Chạy: spawn bot → nhận transcript → valid webhook → analysis → dashboard → stop bot → deletion/retention check.
3. Test riêng: webhook tampered, replay/duplicate, transcript revision muộn.
4. Redact transcript/speaker trong screenshot/log; lưu consent tách biệt, không đưa vào repository.
5. Báo số lần run, success rate, failure mode, không báo F1 sentiment.

**Ghi vào luận văn:** “E2E chứng minh khả năng tích hợp vận hành trong `<N>` run có consent ở môi trường `<...>`; không đại diện cho benchmark ASR hoặc chất lượng sentiment.”

### Task P2-02 — User comprehension/usability study

**Loại:** `[TN] [CONSENT]`.

**Chỉ làm khi:** có quy trình consent, người tham gia phù hợp và dữ liệu dashboard an toàn/synthetic.

**Step by step**

1. Viết 4 task: tìm evidence; nhận biết low effective coverage; so revision/model version; giải thích vì sao output không đánh giá con người.
2. Tuyển 5–10 người dùng mục tiêu; dùng fixture synthetic/redacted.
3. Ghi task completion, thời gian, câu trả lời comprehension, SUS (nếu dùng), phản hồi mở.
4. Phân tích mô tả; không suy luận hiệu quả phổ quát từ mẫu nhỏ.
5. Chỉ sau đó mới viết dashboard “giúp người dùng hiểu giới hạn”; nếu chưa làm chỉ viết “được thiết kế nhằm hỗ trợ”.

---

## 7. Nhánh nâng cấp ML — chỉ chọn nếu muốn giữ claim sentiment model

### Task ML-01 — Corpus và annotation

**Loại:** `[TN] [CONSENT]`.

1. Định nghĩa nhãn positive/neutral/negative/unknown, phủ định, mỉa mai, code-switch, quote và thiếu ngữ cảnh.
2. Thu thập transcript họp có consent hoặc dataset có license phù hợp; lập datasheet/manifest/hash.
3. Có ít nhất 2 annotator độc lập, sau đó adjudication.
4. Tính Cohen's kappa/Krippendorff's alpha và phân bố nhãn.
5. Split train/validation/test theo **meeting**, khóa test set trước tuning.

### Task ML-02 — Baseline ML, Transformer và đánh giá

**Loại:** `[CODE] [TN]`.

1. Train TF-IDF + Logistic Regression làm baseline học máy.
2. Fine-tune PhoBERT (có thể thêm XLM-R nếu đủ thời gian) trên cùng split.
3. Version hóa dataset, preprocessing, tokenizer, seed, hyperparameter, checkpoint, hardware.
4. Báo Macro-F1 CI bootstrap theo meeting, F1 từng lớp, confusion matrix, coverage, P50/P95 inference, calibration và error analysis.
5. Deploy chính artifact tốt nhất qua adapter; chạy lại Task P1-01 để kiểm chứng integration.

**Bảng kết quả ML phải có:**

| Model | Dataset/test version | Macro-F1 [95% CI] | Positive F1 | Neutral F1 | Negative F1 | Coverage | P95 inference |
|---|---|---:|---:|---:|---:|---:|---:|
| TF-IDF + LR | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` |
| PhoBERT fine-tune | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` | `<...>` |

Không dùng notebook trầm cảm hay social-media dataset khác task để điền vào bảng này mà không ghi rõ domain shift và giới hạn.

---

## 8. Thứ tự thực hiện đề xuất (7–10 ngày)

1. **Ngày 1:** P0-01, P0-02, P0-03 — chốt scope, sửa placeholder, khởi tạo evidence format.
2. **Ngày 2:** P0-04, P0-05 — chạy unit + smoke, lưu evidence thật.
3. **Ngày 3–4:** P0-06, P0-07 — benchmark pipeline nội bộ, coverage/aggregate sửa đúng logic.
4. **Ngày 5:** P1-01 — adapter thứ hai và integration evidence.
5. **Ngày 6:** P1-02 — failure/recovery tests.
6. **Ngày 7:** P0-08, P0-09, P1-03, P1-04 — related work, DSR/RQ, văn phong, notebook scope.
7. **Ngày 8–9:** điền Chương 8 bằng số liệu thật; thêm threats to validity và appendix evidence.
8. **Ngày 10:** build PDF, rà soát claim/bảng rỗng, rehearsal 30 câu phản biện.

Nếu không đủ thời gian, thứ tự không được bỏ là: **P0-01 → P0-02 → P0-03 → P0-04 → P0-05 → P0-06 → P0-09**.

---

## 9. Checklist cuối trước nộp

- [ ] Mỗi số trong Chương 8 có Evidence ID, command, thời điểm và môi trường.
- [ ] Không gọi fixture synthetic là data meeting thực.
- [ ] Không gọi latency pipeline nội bộ là Vexa/ASR end-to-end.
- [ ] Không gọi rule baseline là PhoBERT/model ML.
- [ ] Không dùng confidence baseline như xác suất đúng.
- [ ] Không kết luận dashboard đã ngăn diễn giải sai nếu chưa có user study.
- [ ] Không còn bảng trống/placeholder/“sẽ điền sau”.
- [ ] Mọi RQ có trạng thái bằng chứng trung thực.
- [ ] PDF build không có warning tham chiếu quan trọng; danh mục hình/bảng đúng.
