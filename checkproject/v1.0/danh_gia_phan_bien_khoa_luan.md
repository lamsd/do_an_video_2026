# BÁO CÁO PHẢN BIỆN VÀ GÓP Ý KHÓA LUẬN

**Tài liệu được phản biện:** *Hệ thống phân tích sắc thái cảm xúc từ transcript tiếng Việt trong họp trực tuyến*  
**Phạm vi phản biện:** nội dung học thuật, logic nghiên cứu, thiết kế thực nghiệm, mô hình/dữ liệu, kiến trúc hệ thống, mức độ đóng góp, khả năng bảo vệ, văn phong và hình thức.  
**Cách chấm:** theo góc nhìn một hội đồng phản biện khóa luận ngành Khoa học Máy tính. Điểm số bên dưới chỉ là rubric mô phỏng để chỉ ra mức độ sẵn sàng, không thay thế thang điểm chính thức của trường.

---

## 1. Kết luận phản biện ngắn gọn

Bản luận văn có **điểm mạnh rõ rệt về tư duy kiến trúc phần mềm, khả năng truy vết dữ liệu, quản trị version, privacy-by-design và việc tự giới hạn phạm vi tuyên bố**. Tác giả thể hiện sự thận trọng khi phân biệt sentiment với emotion và sức khỏe tâm thần; đồng thời không lấy kết quả từ notebook trầm cảm để suy diễn sang bài toán sentiment.

Tuy nhiên, ở trạng thái hiện tại, luận văn có một vấn đề cốt lõi:

> **Phần “nghiên cứu và thực nghiệm” chưa đủ bằng chứng để đỡ cho tiêu đề và mục tiêu của một khóa luận về hệ thống phân tích sentiment.**

Runtime thực tế chỉ là `baseline-rules-v2`, không phải mô hình học máy; chưa có corpus transcript họp được gán nhãn đúng task; chưa có Macro-F1/Accuracy; chưa có WER/CER; chưa có latency benchmark; chưa có user study; nhiều bảng trong Chương 8 vẫn là **mẫu để điền sau**. Do đó, bản hiện tại giống một **báo cáo thiết kế kiến trúc + kế hoạch nghiên cứu + MVP kỹ thuật** hơn là một khóa luận đã hoàn tất phần thực nghiệm.

Nếu nộp/bảo vệ ngay, câu hỏi nguy hiểm nhất từ hội đồng sẽ là:

> “Em gọi đây là hệ thống phân tích sentiment, nhưng em chưa chứng minh hệ thống phân tích đúng đến mức nào. Vậy đóng góp khoa học của khóa luận nằm ở đâu, khác gì một đồ án tích hợp phần mềm?”

Đây là vấn đề cần xử lý trước tiên.

---

# 2. Đánh giá tổng thể theo tiêu chí

| Hạng mục | Đánh giá mô phỏng | Nhận xét |
|---|---:|---|
| Xác định phạm vi và ranh giới bài toán | 8/10 | Rất thận trọng, phân biệt sentiment với depression/clinical inference tốt. |
| Cấu trúc luận văn | 7/10 | Có logic từ pipeline → model → backend → UI → hạ tầng → kiểm chứng. |
| Tổng quan nghiên cứu | 4/10 | Nặng “cơ sở lý thuyết”, thiếu related work thực sự và research gap. |
| Phương pháp nghiên cứu | 5/10 | Có nhắc Design Science nhưng chưa triển khai thành methodology chặt chẽ. |
| Dữ liệu và thực nghiệm ML | 2/10 | Gần như chưa có kết quả thực nghiệm về sentiment. |
| Kiểm chứng hệ thống | 5/10 | Có test design và smoke test, nhưng bằng chứng chạy thực tế còn thiếu/không được điền. |
| Kiến trúc phần mềm | 8/10 | Đây là phần mạnh nhất của luận văn. |
| Novelty/đóng góp khoa học | 4/10 | Chưa được chứng minh rõ; phần lớn là integration/design pattern chuẩn. |
| Reproducibility | 6/10 | Thiết kế reproducibility tốt, nhưng evidence bundle thực tế chưa xuất hiện đầy đủ. |
| Văn phong học thuật | 6.5/10 | Khá rõ nhưng pha quá nhiều thuật ngữ Anh–Việt và hơi giống tài liệu engineering. |
| Mức độ sẵn sàng để bảo vệ | 4–5/10 | **Chưa nên xem là bản final nếu chưa bổ sung evidence/thực nghiệm.** |

### Nhận định tổng hợp

- Nếu chấm như **một báo cáo thiết kế hệ thống kỹ thuật**: khá tốt.
- Nếu chấm như **một khóa luận Khoa học Máy tính về sentiment analysis**: phần thực nghiệm hiện quá yếu.
- Nếu tác giả muốn giữ cấu trúc hiện tại, nên **đổi trọng tâm/tiêu đề sang thiết kế và kiểm chứng kiến trúc**.
- Nếu muốn giữ tiêu đề hiện tại, phải **bổ sung một mô hình sentiment thật và đánh giá định lượng**.

---

# 3. Điểm mạnh cần giữ

## 3.1. Phạm vi tuyên bố rất có kỷ luật

Luận văn không biến sentiment thành diagnosis, không dùng transcript để kết luận trầm cảm và không tuyên bố output là đánh giá con người. Đây là một điểm học thuật rất tốt.

Ở Chương 1 và Chương 2, tác giả phân biệt:

- sentiment;
- emotion/intent;
- đánh giá lâm sàng;
- PHQ-9/DSM-5;
- output hệ thống và quyết định của con người.

Phần này nên giữ, nhưng có thể rút gọn để dành chỗ cho thực nghiệm.

## 3.2. Tư duy provenance/versioning tốt

Các khái niệm:

- `source_revision`;
- `model_version`;
- `preprocessing_version`;
- `is_current`;
- evidence từ aggregate → prediction → unit → segment;
- outbox/idempotency;

được tổ chức khá chặt chẽ.

Đây là một đóng góp kỹ thuật đáng giá nếu tác giả xác định đề tài theo hướng **auditable / traceable meeting intelligence system**.

## 3.3. Phân biệt “đã triển khai” và “đề xuất” khá rõ

Luận văn nhiều lần ghi:

- Google Meet + Vexa: phạm vi hiện tại;
- Teams/Zoom/Jitsi: hướng mở rộng;
- MLflow: kiến trúc đề xuất;
- PhoBERT/custom model: chưa serving;
- Kubernetes/HA/autoscaling: chưa kiểm chứng.

Đây là cách viết đúng, tránh overclaim.

## 3.4. Chương 8 có tư duy đánh giá đúng hướng

Các đề xuất về:

- split theo meeting;
- tránh leakage theo segment;
- Macro-F1;
- class-wise precision/recall/F1;
- calibration;
- bootstrap theo meeting;
- error analysis;
- WER/CER;
- latency P50/P95/P99;
- UX evaluation;

đều hợp lý về phương pháp.

Vấn đề không phải là thiết kế đánh giá sai, mà là **luận văn chưa thực hiện chính thiết kế đánh giá mà nó đề xuất**.

---

# 4. Các lỗi/nguy cơ nghiêm trọng nhất

## CRITICAL-01 — Không có kết quả thực nghiệm sentiment thực sự

Đây là lỗi lớn nhất.

Tóm tắt ghi rõ:

- PhoBERT/custom model chỉ là lựa chọn lý thuyết;
- runtime là `baseline-rules-v2`;
- không báo cáo chất lượng sentiment;
- không báo cáo WER;
- không báo cáo latency;
- bảng so sánh model để điền sau.

Ở Chương 4, luận văn còn xác nhận `baseline-rules-v2`:

- không phải ML model;
- confidence không calibrated;
- chỉ dùng kiểm tra data contract/pipeline.

### Vì sao nguy hiểm khi bảo vệ?

Vì tiêu đề đề cập trực tiếp đến **hệ thống phân tích sắc thái cảm xúc**, trong khi luận văn chưa chứng minh:

> “Nhãn positive/neutral/negative do hệ thống tạo ra có độ tin cậy khoa học nào?”

Hội đồng hoàn toàn có thể hỏi:

1. Accuracy/F1 là bao nhiêu?
2. Dataset nào?
3. Ai gán nhãn?
4. Có train/test leakage không?
5. Vì sao chọn PhoBERT?
6. PhoBERT đã thực sự được chạy chưa?
7. Nếu model hiện tại chỉ là luật, đóng góp về AI/NLP nằm ở đâu?

### Cách sửa

Có hai hướng.

#### Hướng A — Giữ đề tài sentiment

Phải bổ sung tối thiểu:

- dataset đúng task;
- guideline nhãn;
- train/validation/test split theo meeting;
- ít nhất một baseline ML;
- ít nhất một Transformer model;
- Macro-F1;
- precision/recall/F1 từng lớp;
- confusion matrix;
- error analysis;
- inference latency;
- mô tả hardware;
- version dataset/model.

#### Hướng B — Không đủ thời gian train/evaluate model

Đổi trọng tâm thành:

> **Thiết kế và kiểm chứng kiến trúc hệ thống xử lý transcript tiếng Việt có khả năng tích hợp bộ phân loại sentiment**

Khi đó đóng góp là:

- provenance;
- revision;
- adapter;
- event-driven processing;
- evidence;
- auditability;
- privacy boundary;
- integration verification.

Hướng B phù hợp hơn với những gì tài liệu hiện thực sự có.

---

## CRITICAL-02 — Chương “Kết quả/kiểm chứng” vẫn chứa bảng mẫu trống

Chương 8 có:

- Bảng 8.2: mẫu so sánh model;
- Bảng 8.3: mẫu evidence integration;
- nhiều mục nói “sẽ điền sau”, “chỉ điền khi run”.

Đây là dấu hiệu rất rõ của **tài liệu chưa hoàn tất**.

Một khóa luận final không nên có “mẫu kết quả để điền sau” ở chương thực nghiệm.

### Cách sửa

Mỗi bảng phải thuộc một trong hai loại:

**A. Kết quả thật**

Ví dụ:

| Metric | Result |
|---|---:|
| Unit tests | 11/11 pass |
| Integration test | 5/5 pass |
| E2E runs | 20 |
| Success rate | ... |
| P50 latency | ... ms |
| P95 latency | ... ms |
| Coverage | ... |
| Failure cases | ... |

**B. Protocol tương lai**

Nếu chưa thực hiện, chuyển bảng sang:

- Chương “Hướng phát triển”, hoặc
- Phụ lục “Protocol đánh giá đề xuất”.

Không để một bảng trống trong chương mang tên “Kiểm chứng”.

---

## CRITICAL-03 — Có mâu thuẫn giữa cụm “đã kiểm chứng” và evidence thực tế

Nhiều chương dùng các cụm như:

- “luồng đã kiểm chứng”;
- “topology đã kiểm chứng”;
- “MVP đã xây dựng”;
- “runtime đã kiểm chứng”.

Nhưng Chương 8 lại viết rất đúng rằng:

> Một script tồn tại trong repository không đồng nghĩa với test đã chạy.

Và bảng evidence integration vẫn trống.

### Vấn đề

Nếu không có:

- log;
- timestamp;
- commit/image digest;
- command;
- exit code;
- screenshot/API result;
- result summary;

thì từ “đã kiểm chứng” dễ bị hội đồng bắt bẻ.

### Cách sửa

Mọi chỗ “đã kiểm chứng” phải có một ID evidence, ví dụ:

- `EVID-UT-001`;
- `EVID-INT-001`;
- `EVID-E2E-001`.

Tạo bảng:

| Evidence ID | Test | Commit | Environment | Result | Artifact |
|---|---|---|---|---|---|
| EVID-UT-001 | pytest backend | abc123 | Docker local | 11/11 PASS | appendix/log |
| EVID-INT-001 | smoke pipeline | abc123 | Docker local | PASS | appendix/log |

Sau đó trong luận văn chỉ dùng “đã kiểm chứng” khi có evidence tương ứng.

---

## CRITICAL-04 — Câu hỏi nghiên cứu số 2 chưa được chứng minh

RQ2 hỏi đại ý:

> Adapter có cho phép thay bộ phân loại hiện tại bằng PhoBERT/model artifact mà không đổi API, persistence và dashboard không?

Nhưng luận văn không có:

- PhoBERT serving;
- TF-IDF adapter serving;
- custom model adapter serving;
- test swap A → B.

Do đó RQ2 hiện mới chứng minh được ở mức **thiết kế interface**, chưa chứng minh được ở mức **thực nghiệm**.

### Cách sửa đơn giản

Không nhất thiết phải fine-tune PhoBERT để test kiến trúc.

Có thể triển khai thêm một classifier adapter thứ hai, ví dụ:

- `DummyClassifierAdapter`;
- `TFIDFLogisticRegressionAdapter`;
- hoặc một artifact pretrained phù hợp.

Sau đó chạy cùng fixture với:

1. baseline adapter;
2. adapter thứ hai.

Chứng minh:

- API không đổi;
- DB schema không đổi;
- frontend không đổi;
- chỉ đổi `MODEL_VERSION` / model URI;
- `model_version` trong evidence thay đổi đúng.

Như vậy RQ2 mới có bằng chứng trực tiếp.

---

## CRITICAL-05 — RQ4 mới chỉ mô tả UI, chưa chứng minh người dùng “không diễn giải quá mức”

RQ4 hỏi cách biểu diễn evidence/confidence/coverage **để tránh** coi output là kết luận về con người.

Nhưng không có user study.

Do đó hiện chỉ có thể kết luận:

> “Dashboard được thiết kế với mục tiêu giảm nguy cơ diễn giải quá mức.”

Không thể kết luận:

> “Dashboard giúp người dùng tránh diễn giải sai.”

### Cách sửa

Nếu không có user study, sửa wording của RQ4 thành câu hỏi thiết kế:

> “Dashboard biểu diễn evidence, confidence và coverage theo những nguyên tắc nào để truyền đạt giới hạn của output?”

Nếu muốn giữ từ “tránh”, cần usability study / comprehension study.

---

# 5. Phản biện sâu về metric và logic kỹ thuật

## 5.1. Coverage hiện tại có thể gây hiểu lầm

Luận văn định nghĩa:

\[
coverage = P/A
\]

trong đó:

- `A`: số unit qua quality gate;
- `P`: số unit có prediction khác `unknown`.

Vấn đề:

Giả sử:

- tổng cộng 100 unit;
- 90 unit bị quality gate loại;
- 10 unit accepted;
- cả 10 được model predict.

Khi đó:

- `coverage = 10/10 = 100%`.

Nhưng thực tế hệ thống chỉ phân tích được **10% nội dung ban đầu**.

### Khuyến nghị

Tách thành ít nhất ba metric:

1. **Acceptance rate**

\[
acceptance\_rate = A/T
\]

2. **Prediction coverage**

\[
prediction\_coverage = P/A
\]

3. **Effective coverage**

\[
effective\_coverage = P/T
\]

Trong đó `T` là tổng số unit/segment đủ điều kiện được xem xét trước quality gate, tùy định nghĩa pipeline.

Dashboard nên hiển thị ít nhất:

- tỷ lệ dữ liệu bị loại;
- prediction coverage;
- effective coverage.

---

## 5.2. Công thức aggregate đang dùng confidence theo cách chưa được chứng minh

Luận văn định nghĩa:

\[
p_i=P_i(positive)-P_i(negative)
\]

\[
w_i=\max(1,token_i)\times confidence_i
\]

và dùng weighted average để tạo `score_window`.

Trong khi chính luận văn thừa nhận:

- confidence của baseline là điểm theo luật;
- chưa calibrated;
- không phải xác suất đúng.

### Mâu thuẫn

Nếu confidence chưa có ý nghĩa xác suất, dùng nó làm **trọng số định lượng** có thể làm aggregate trở nên tùy ý.

Ngoài ra, nhân thêm `token_i` làm unit dài có trọng số lớn hơn unit ngắn nhưng chưa có bằng chứng rằng phát ngôn dài phải có ảnh hưởng sentiment lớn hơn.

### Hội đồng có thể hỏi

> “Tại sao 20 token phải có trọng số gấp đôi 10 token?”

> “Confidence chưa calibrated thì tại sao dùng confidence để weighting?”

> “Có sensitivity analysis cho công thức này không?”

### Cách sửa

Một trong các hướng:

- aggregate theo count của predicted labels;
- dùng mean probability nếu model probability đã calibrated;
- báo cả unweighted và weighted result;
- chạy sensitivity analysis;
- hoặc tuyên bố score chỉ là heuristic visualization và không dùng như metric nghiên cứu.

Nếu giữ công thức hiện tại, phải có lý do và đánh giá.

---

## 5.3. Các threshold preprocessing đang mang tính heuristic

Các rule:

- dưới 3 token → reject;
- tối đa 3 segment;
- cửa sổ 45 giây;
- duplicate “gần nhau”;
- heuristic nhận diện tiếng Việt;
- hallucination pattern;

đều ảnh hưởng trực tiếp đến output.

Nhưng chưa có:

- ablation;
- pilot study;
- sensitivity analysis;
- dataset statistics;
- error analysis.

### Cách sửa

Tạo bảng:

| Parameter | Current | Rationale | Evaluated? |
|---|---:|---|---|
| min tokens | 3 | tránh fragment quá ngắn | chưa |
| max segments/unit | 3 | giữ context ngắn | chưa |
| max window | 45s | giới hạn context/latency | chưa |

Sau đó thử một vài cấu hình hợp lý và báo tác động lên:

- số unit;
- rejection rate;
- coverage;
- F1 nếu có label.

---

# 6. Vấn đề về research gap và related work

Chương 2 hiện giống **cơ sở lý thuyết** hơn là **tổng quan nghiên cứu**.

Có:

- BERT;
- PhoBERT;
- XLM-R;
- model card;
- data provenance;
- GDPR;
- calibration.

Nhưng thiếu một synthesis kiểu:

> Các công trình trước đã làm gì?  
> Họ dùng dataset nào?  
> Task nào?  
> Metric nào?  
> Hạn chế nào?  
> Khoảng trống mà luận văn này xử lý là gì?

### Nên có một bảng related work

| Work | Domain | Language | Input | Model | Evaluation | Limitation relevant to this thesis |
|---|---|---|---|---|---|---|
| Study A | social media | Vietnamese | clean text | PhoBERT | F1 | không phải ASR transcript |
| Study B | meeting | English | ASR | Transformer | ... | không hỗ trợ Vietnamese |
| Study C | conversational sentiment | multilingual | dialogue | XLM-R | ... | không có provenance/versioning |

Sau bảng, viết rõ **research gap**.

Ví dụ:

> Existing Vietnamese sentiment studies chủ yếu đánh giá trên review/social media text; meeting transcript có ASR noise, revisions, speaker boundaries và operational provenance nhưng chưa được xử lý đồng thời trong một auditable pipeline.

Lưu ý: câu trên chỉ được viết nếu bạn tìm được tài liệu chứng minh.

---

# 7. Novelty hiện chưa rõ

Các thành phần:

- FastAPI;
- PostgreSQL;
- Valkey;
- outbox;
- worker;
- SSE;
- Docker Compose;
- adapter;
- model versioning;

đều là các kỹ thuật phổ biến.

Không có nghĩa đề tài “không có đóng góp”, nhưng luận văn phải nói rõ đóng góp nằm ở **cách kết hợp và đánh giá trong context cụ thể**, chứ không phải từng công nghệ.

### Không nên viết đóng góp theo kiểu

> “Sử dụng PostgreSQL, Valkey, SSE, FastAPI...”

### Nên viết

> “Đề xuất và kiểm chứng một data contract có revision-aware provenance cho transcript ASR, cho phép tái lập prediction theo source revision, preprocessing version và model version.”

Đây mới là contribution có tính khái quát.

---

# 8. Phương pháp nghiên cứu Design Science chưa đủ chặt

Luận văn có nhắc Design Science Research, nhưng hiện mới dùng nó như một câu giải thích cho việc xây artefact.

Cần làm rõ:

1. **Problem identification**
2. **Objectives of solution**
3. **Artefact design**
4. **Implementation**
5. **Demonstration**
6. **Evaluation**
7. **Communication**

Sau đó map từng bước sang chương/bằng chứng.

Ví dụ:

| DSR step | Thesis evidence |
|---|---|
| Problem | ASR transcript noisy/revised, sentiment output dễ bị overinterpret |
| Objective | traceability, replaceable classifier, near-real-time |
| Artefact | contracts + pipeline + dashboard |
| Demonstration | fixture/smoke test |
| Evaluation | unit/integration/latency/model/UX |
| Limitations | Chapter 8/10 |

Hiện bước **Evaluation** là bước yếu nhất.

---

# 9. Nhận xét theo từng chương

## Trang bìa và phần đầu

### Lỗi bắt buộc sửa

Trang bìa vẫn còn:

- `[CẦN ĐIỀN: Họ và tên sinh viên]`;
- `[CẦN ĐIỀN: MSSV]`;
- `[CẦN ĐIỀN: Tên lớp]`;
- tháng/năm chưa điền.

Lời cam đoan cũng còn placeholder.

Đây là lỗi hình thức nghiêm trọng nếu là bản nộp.

### Abstract không đồng bộ hoàn toàn với Tóm tắt

Tóm tắt tiếng Việt có mục **Kết luận** nhưng Abstract tiếng Anh dừng sau Results rồi Keywords.

Nên đồng bộ cấu trúc.

---

## Chương 1 — Giới thiệu

### Điểm tốt

- phạm vi rõ;
- có research questions;
- biết giới hạn claim.

### Cần sửa

**RQ2 chưa có thực nghiệm thay model.**

**RQ4 mang tính đánh giá hiệu quả UI nhưng không có user study.**

**Đóng góp dự kiến** nên đổi thành **đóng góp của khóa luận** ở bản final.

Nếu vẫn viết “dự kiến” trong bản cuối, hội đồng sẽ hỏi:

> “Vậy đóng góp nào đã hoàn thành?”

---

## Chương 2 — Tổng quan và cơ sở lý thuyết

### Điểm tốt

Phân biệt sentiment/emotion/clinical tốt.

### Điểm yếu

Thiếu:

- literature comparison;
- Vietnamese sentiment datasets;
- conversational sentiment;
- sentiment on ASR transcripts;
- effect of ASR noise on downstream classification;
- meeting intelligence related work;
- explicit research gap.

### Góp ý

Tách Chương 2 thành:

1. Background
2. Related work
3. Research gap

---

## Chương 3 — Dữ liệu và pipeline

### Điểm tốt

Data contract và revision logic khá tốt.

### Điểm cần phản biện

- threshold 3 token chưa có evidence;
- 3 segments chưa có evidence;
- 45 s chưa có evidence;
- dedup rule chưa đánh giá false positive;
- language heuristic chưa benchmark;
- coverage definition chưa phản ánh rejected data;
- aggregate weighting thiếu validation.

Đây là chương cần bổ sung experimental justification.

---

## Chương 4 — Model lifecycle

### Điểm tốt

MLOps thinking tốt.

### Vấn đề lớn

Chương này khá dài nhưng phần lớn là:

- “nên”;
- “cần”;
- “đề xuất”;
- “sau này”;
- “khi có dataset”.

Trong khi model thật lại chưa có.

Điều này tạo cảm giác luận văn mô tả một **target architecture** thay vì báo cáo kết quả nghiên cứu.

### Cách sửa

Nếu không triển khai MLflow/model thật:

- rút gọn Chương 4;
- chuyển MLflow/retraining/canary/shadow sang Future Work;
- dùng phần tiết kiệm được để thêm actual experiments.

---

## Chương 5 — Backend

Đây là phần tương đối mạnh.

Tuy nhiên, cần tăng bằng chứng:

- API contract test;
- transaction behavior;
- duplicate webhook test;
- queue recovery;
- worker crash/restart;
- stale revision;
- consistency khi retry.

Không chỉ mô tả mechanism.

---

## Chương 6 — Dashboard

Thiết kế an toàn về interpretation tốt.

Nhưng:

- chưa user study;
- chưa accessibility audit;
- timeline click còn tải toàn evidence thay vì window;
- chưa login/authorization production.

Không nên trình bày UX như đã chứng minh hiệu quả.

---

## Chương 7 — Hạ tầng

Nội dung đúng về engineering nhưng hơi nhiều so với phần ML thực nghiệm.

Nếu khóa luận giữ hướng AI/NLP, nên rút phần:

- secret manager;
- HA;
- Kubernetes;
- multi-region;
- RTO/RPO;
- service mesh;

xuống Future Work/Appendix.

Chỉ giữ những gì trực tiếp liên quan đến reproducibility của experiment.

---

## Chương 8 — Chương yếu nhất hiện tại

Tên chương là:

> “Kiểm chứng ứng dụng và thiết kế thực nghiệm”

Nhưng phần lớn nội dung vẫn là:

- tiêu chí cần đo;
- protocol tương lai;
- bảng mẫu;
- không có kết quả.

### Chương 8 final nên đổi thành cấu trúc

1. Experimental setup
2. Dataset
3. Annotation
4. System configuration
5. Unit test results
6. Integration results
7. Model results
8. Performance results
9. Error analysis
10. Threats to validity

### Nguyên tắc

**Không có bảng trống.**

---

## Chương 9 — Privacy/Ethics

Phần này có chất lượng tốt nhưng đang chiếm tỷ trọng lớn so với evidence experimental.

Nên giữ nhưng rút:

- các nguyên tắc chính;
- consent;
- retention;
- access control;
- interpretation boundary.

Phần compliance roadmap chi tiết có thể chuyển appendix/future work.

---

## Chương 10 — Kết luận

Phần này trung thực.

Tuy nhiên, cần có một subsection:

### “Trả lời câu hỏi nghiên cứu”

Ví dụ:

**RQ1 — Supported:** test A/B/C chứng minh...  
**RQ2 — Partially supported:** interface được thiết kế nhưng chưa swap với ML artifact thật...  
**RQ3 — Partially supported:** internal pipeline pass, Vexa E2E chưa có...  
**RQ4 — Design-only evidence:** UI thể hiện ..., chưa có user study.

Cách này giúp hội đồng thấy tác giả tự kiểm soát claim rất tốt.

---

# 10. Vấn đề văn phong và thuật ngữ

Luận văn dùng rất nhiều từ Anh xen tiếng Việt:

- transcript;
- evidence;
- quality gate;
- language router;
- analysis unit;
- serving;
- runtime;
- artifact;
- promote;
- shadow mode;
- canary;
- source of truth;
- ownership;
- fallback;
- replay;
- reconcile;
- latency;
- coverage.

Điều này làm văn phong giống design document của engineering team hơn là luận văn tiếng Việt.

### Khuyến nghị

Ở lần xuất hiện đầu:

> đơn vị phân tích (analysis unit)

Sau đó ưu tiên dùng:

> đơn vị phân tích

Tương tự:

- evidence → bằng chứng truy vết;
- quality gate → bộ kiểm tra chất lượng;
- runtime → môi trường thực thi;
- serving → phục vụ suy luận;
- custom model → mô hình tùy biến;
- source of truth → nguồn dữ liệu chuẩn;
- coverage → độ bao phủ dự đoán.

Không cần dịch tên API/code identifier.

---

# 11. Lỗi hình thức/tài liệu

## Bắt buộc

- Điền đầy đủ thông tin trang bìa.
- Điền lời cam đoan.
- Kiểm tra template trường về Lời cảm ơn.
- Thêm **Danh mục hình** vì tài liệu có nhiều Hình 3.1, 4.1, 5.1, 6.1, 6.2, 7.1.
- Kiểm tra có cần Phụ lục hay không.
- Kiểm tra capitalization trong tài liệu tham khảo.
- Chuẩn hóa thuật ngữ Anh–Việt.
- Không để bảng kết quả trống.

## Nên có phụ lục

- API endpoint summary;
- DB schema;
- test commands;
- evidence log;
- environment/hardware;
- model config;
- annotation guideline;
- example redacted transcript;
- error cases.

---

# 12. Những câu hội đồng rất có thể hỏi

1. Đóng góp khoa học chính của đề tài là gì?
2. Nếu model hiện tại chỉ là rule baseline thì tại sao gọi đây là sentiment-analysis system?
3. PhoBERT xuất hiện trong tiêu đề/nội dung với vai trò gì nếu chưa được serving?
4. Accuracy/Macro-F1 hiện tại là bao nhiêu?
5. Không có dataset đúng domain thì bạn chứng minh hệ thống phân tích đúng bằng cách nào?
6. Vì sao chọn 3 token?
7. Vì sao ghép tối đa 3 segment?
8. Vì sao cửa sổ 45 giây?
9. Vì sao confidence được dùng làm trọng số dù chưa calibrated?
10. Vì sao unit dài được weight cao hơn unit ngắn?
11. Coverage 100% có thể xảy ra khi phần lớn transcript đã bị reject không?
12. RQ2 nói model có thể thay thế; bạn đã thử thay model thật chưa?
13. Bạn chứng minh event-driven architecture tốt hơn synchronous architecture bằng gì?
14. Vì sao chọn SSE thay WebSocket?
15. “Near-real-time” được định nghĩa bằng con số nào?
16. Có bao nhiêu meeting đã chạy?
17. Vexa E2E đã thực hiện bao nhiêu lần?
18. Có log nào chứng minh test đã pass?
19. Nếu transcript bị sửa sau prediction thì consistency được xử lý thế nào?
20. Nếu cùng một webhook gửi lại nhiều lần thì hệ thống xử lý ra sao?
21. Nếu worker chết sau commit nhưng trước ACK thì điều gì xảy ra?
22. Nếu confidence không phải probability thì UI nên hiển thị như thế nào?
23. Sentiment có ích cụ thể cho user nào trong meeting?
24. Business/use-case nào thực sự cần feature này?
25. Vì sao ethical/privacy chapter dài nhưng user study/model study chưa có?
26. Nếu không dùng sentiment để đánh giá con người, dashboard này hỗ trợ quyết định gì?
27. Research gap của bạn so với các hệ thống meeting intelligence hiện có là gì?
28. Contribution nào có thể publish thành paper?
29. Threats to validity của experiment là gì?
30. Nếu có thêm 2 tuần, việc gì quan trọng nhất cần hoàn thành?

---

# 13. Kế hoạch chỉnh sửa ưu tiên

## P0 — Phải sửa trước khi xem là bản final

- [ ] Điền toàn bộ placeholder ở trang bìa/lời cam đoan.
- [ ] Chọn rõ hướng đề tài: **system architecture** hoặc **sentiment ML**.
- [ ] Không để bảng 8.2/8.3 trống.
- [ ] Chạy thật unit/integration tests và lưu evidence.
- [ ] Có bảng kết quả kiểm chứng với số liệu.
- [ ] Sửa các câu “đã kiểm chứng” nếu chưa có log thực tế.
- [ ] Trả lời từng Research Question trong Chương 10.
- [ ] Sửa coverage metric.
- [ ] Giải thích hoặc loại bỏ confidence-weighted polarity formula.
- [ ] Bổ sung research gap.

## P1 — Rất nên sửa trước bảo vệ

- [ ] Triển khai classifier adapter thứ hai để kiểm chứng RQ2.
- [ ] Đo P50/P95 latency.
- [ ] Thử worker/Valkey failure recovery.
- [ ] Bổ sung threat to validity.
- [ ] Bổ sung list of figures.
- [ ] Chuẩn hóa thuật ngữ Anh–Việt.
- [ ] Rút Chương 4/7/9 nếu chưa triển khai các feature tương lai.

## P2 — Làm luận văn mạnh hơn đáng kể

- [ ] Xây corpus meeting transcript có annotation.
- [ ] So sánh TF-IDF+LR vs PhoBERT vs XLM-R.
- [ ] Đo annotation agreement.
- [ ] Calibration analysis.
- [ ] Error analysis theo ASR noise/code-switching/negation.
- [ ] User study dashboard.
- [ ] Ablation/sensitivity cho quality gate và unit builder.

---

# 14. Hai hướng “cứu” luận văn

## Phương án 1 — Nhanh và phù hợp nhất với tài liệu hiện tại

### Đổi framing

**Tiêu đề đề xuất:**

> **Thiết kế và kiểm chứng kiến trúc hệ thống phân tích sentiment từ transcript tiếng Việt trong họp trực tuyến**

Hoặc:

> **Hệ thống xử lý transcript họp trực tuyến có khả năng truy vết và tích hợp mô hình phân tích sentiment tiếng Việt**

### Đóng góp tập trung

- revision-aware transcript;
- classifier adapter;
- provenance;
- asynchronous pipeline;
- evidence;
- privacy-aware dashboard;
- reproducible integration tests.

### Phải bổ sung

- test evidence thật;
- latency system;
- failure/recovery test;
- second adapter;
- RQ answer table.

Hướng này không bắt buộc phải có một nghiên cứu ML lớn, nhưng phải làm evaluation artefact nghiêm túc.

---

## Phương án 2 — Giữ luận văn theo hướng AI/NLP sentiment

Phải bổ sung:

1. Corpus sentiment phù hợp.
2. Annotation guideline.
3. Annotator agreement.
4. Meeting-level split.
5. TF-IDF + Logistic Regression.
6. PhoBERT fine-tune.
7. Có thể thêm XLM-R.
8. Macro-F1 + class metrics.
9. Confusion matrix.
10. Calibration.
11. Error analysis.
12. Inference latency.

Khi đó architecture sẽ là phần deployment hỗ trợ cho model research.

---

# 15. Gợi ý viết lại “Đóng góp”

Phiên bản hiện tại mô tả khá nhiều component. Nên cô đọng thành 3–4 contribution có khả năng kiểm chứng.

Ví dụ:

### Contribution 1 — Revision-aware transcript provenance

Đề xuất data contract cho phép liên kết mỗi prediction với transcript segment, source revision, preprocessing version và model version, hỗ trợ tái lập và supersede kết quả khi transcript thay đổi.

### Contribution 2 — Replaceable classifier boundary

Thiết kế `SentimentClassifier` contract tách model khỏi API, persistence và dashboard; đánh giá bằng việc thay đổi ít nhất hai adapter mà không sửa các interface còn lại.

### Contribution 3 — Recoverable asynchronous processing

Hiện thực pipeline PostgreSQL–Valkey–worker với idempotency, queued-run recovery và outbox event; đánh giá qua integration/failure tests.

### Contribution 4 — Evidence-aware output

Thiết kế dashboard hiển thị prediction cùng coverage/evidence/revision thay vì chỉ hiển thị một sentiment score.

Lưu ý: contribution 2–4 chỉ nên tuyên bố “đã kiểm chứng” sau khi có test/result.

---

# 16. Mẫu cấu trúc Chương 8 nên thay đổi

## 8.1 Experimental questions

RQ/EQ rõ ràng.

## 8.2 Experimental environment

- CPU/GPU;
- RAM;
- OS;
- Docker;
- model;
- dataset version;
- commit.

## 8.3 Dataset

Số:

- meeting;
- speaker;
- segment;
- unit;
- class distribution.

## 8.4 Annotation

- guideline;
- annotators;
- agreement.

## 8.5 Model experiments

| Model | Macro-F1 | Pos F1 | Neu F1 | Neg F1 | Coverage | P95 |
|---|---:|---:|---:|---:|---:|---:|

## 8.6 System integration results

| Test | Runs | Pass | Failure |
|---|---:|---:|---:|

## 8.7 Performance

P50/P95/P99.

## 8.8 Error analysis

Ít nhất các nhóm:

- negation;
- ASR error;
- code-switch;
- sarcasm;
- short utterance;
- speaker error.

## 8.9 Threats to validity

- external validity;
- construct validity;
- label subjectivity;
- dataset size;
- domain shift;
- synthetic fixture limitation.

---

# 17. Nhận xét cuối cùng của phản biện

Tài liệu hiện **không phải một bản viết kém**. Ngược lại, nó cho thấy tác giả có năng lực hệ thống, có tư duy data engineering/backend/MLOps và đặc biệt có ý thức tốt về giới hạn bằng chứng.

Nhưng chính sự trung thực đó cũng làm lộ ra vấn đề chính:

> **Luận văn đang mô tả rất tốt những thí nghiệm cần làm, trong khi chưa trình bày đủ các thí nghiệm đã làm.**

Đây là khác biệt giữa:

- một **proposal/technical design document mạnh**, và
- một **khóa luận hoàn chỉnh có contribution được kiểm chứng**.

Nếu chỉ có thời gian sửa một việc, hãy ưu tiên:

> **Biến Chương 8 từ “protocol/mẫu kết quả” thành “evidence và kết quả thực tế”.**

Nếu chỉ có thời gian sửa hai việc:

1. hoàn thiện Chương 8;
2. điều chỉnh tiêu đề/phạm vi contribution cho khớp bằng chứng.

Nếu có thể đầu tư thêm cho phần AI:

3. thêm một sentiment model thật + dataset + Macro-F1/error analysis.

---

# 18. Checklist trước ngày bảo vệ

- [ ] Không còn `[CẦN ĐIỀN]`.
- [ ] Abstract/Tóm tắt đồng bộ.
- [ ] Tiêu đề phản ánh đúng contribution.
- [ ] Research gap viết rõ trong 1 đoạn.
- [ ] Có bảng related work.
- [ ] Tất cả RQ đều có answer.
- [ ] Không có bảng kết quả trống.
- [ ] Có evidence test thật.
- [ ] Có commit/environment/hardware.
- [ ] Có số liệu system performance.
- [ ] Nếu giữ claim sentiment: có model metrics.
- [ ] Coverage được định nghĩa lại.
- [ ] Aggregate score được biện minh/đánh giá.
- [ ] Threshold preprocessing có rationale.
- [ ] Threats to validity.
- [ ] Danh mục hình.
- [ ] Thuật ngữ Anh–Việt thống nhất.
- [ ] Future work không bị viết như implementation hiện tại.
- [ ] Chuẩn bị câu trả lời cho 30 câu phản biện ở trên.

---

**Mức ưu tiên cuối cùng:**  
**P0 = hoàn thiện bằng chứng thực nghiệm.**  
Kiến trúc hiện tại có thể là nền tảng tốt, nhưng chưa nên để kiến trúc và roadmap thay thế phần kết quả nghiên cứu.
