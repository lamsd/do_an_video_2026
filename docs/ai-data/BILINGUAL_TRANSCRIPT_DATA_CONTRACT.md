# Hợp đồng dữ liệu transcript Việt-Anh

> Trạng thái: đã áp dụng cho pipeline backend và quality gate corpus. Đây là
> contract vận hành, không phải tuyên bố rằng hệ thống đã có model song ngữ đạt
> chất lượng thực nghiệm.

## 1. Mục tiêu

Mục tiêu của thay đổi này là xử lý transcript Việt-Anh hoặc có chuyển mã một cách
an toàn. Hệ thống không được gộp một đoạn tiếng Anh vào unit tiếng Việt rồi gửi cho
model đơn ngữ; cũng không được biến đoạn không đủ bằng chứng thành `neutral`.

## 2. Contract vận hành

| Trường | Nơi lưu | Ý nghĩa |
| --- | --- | --- |
| `TranscriptSegment.language` | transcript nguồn | Metadata thô từ nhà cung cấp, giữ nguyên để đối chiếu. |
| `AnalysisUnit.language` | unit đã xử lý | Route chuẩn: `vi`, `en`, `mixed`, hoặc `unknown`. |
| `AnalysisUnit.language_source` | unit đã xử lý | Lý do route: `content`, `upstream`, `content_override_upstream`, `content_mixed`, hoặc `insufficient_evidence`. |
| `SentimentPrediction.abstention_reason` | prediction | Lý do không kết luận, như `unsupported_language`, `mixed_language_requires_multilingual_model` hoặc `below_confidence_threshold`. |

Language router hiện là heuristic bảo thủ, không phải language-ID model. Dấu hiệu
Việt và Anh cùng xuất hiện trong một segment sẽ tạo `mixed`; text không đủ dấu hiệu
và không có metadata đáng tin sẽ là `unknown`.

Unit builder chỉ ghép các final segment liền kề khi cùng speaker **và cùng language
route**. Vì vậy evidence luôn cho biết chính xác input nào đã đến model.

## 3. Snapshot và revision

Khi API tạo `analysis_run`, backend khóa bản ghi meeting trong transaction, chụp các
final segment chưa bị retracted vào `analysis_run_input_segments`, rồi lưu:

```text
meeting_id + source_revision + model_version + preprocessing_version
+ input_segment_count + source_fingerprint
```

Worker chỉ đọc snapshot này, không đọc lại `transcript_segments` đang có thể thay
đổi. Nếu Vexa sửa transcript sau đó, revision mới sẽ tạo run mới; run cũ vẫn kiểm
tra được và API đánh dấu nó `is_stale=true` thay vì hiển thị ngầm như kết quả mới.

Provider phải gửi tín hiệu retraction rõ ràng (`retracted`, `is_retracted`, hoặc
trạng thái `retracted`/`deleted`/`revoked`). Việc một segment vắng trong snapshot
REST không tự động được hiểu là đã thu hồi, vì một số provider có thể trả snapshot
không đầy đủ.

## 4. Contract corpus huấn luyện

Corpus họp được phê duyệt dùng bốn cột:

```csv
text,label,meeting_id,language
```

- `label`: `negative`, `neutral`, hoặc `positive`.
- `language`: `vi`, `en`, hoặc `mixed` sau khi annotator review.
- `meeting_id`: mã nội bộ ổn định, không chứa URL hoặc tên người.
- `unknown` không đi vào tập train; nó là trạng thái an toàn ở runtime.

Manifest bắt buộc có `language_policy` và `code_switch_policy`. Quality gate báo
cáo phân bố theo ngôn ngữ, chặn language không chuẩn, leakage text và leakage theo
meeting ID.

## 5. Chiến lược dữ liệu đề xuất

1. Thu thập transcript có consent, redaction và quyền sử dụng rõ ràng.
2. Chỉ xuất `analysis unit` đã ổn định; lưu language route, revision và hash ở vùng
   nội bộ, không đưa raw transcript vào Git.
3. Hai annotator gán độc lập polarity và language; adjudication cho bất đồng.
4. Split theo `meeting_id`, khóa test set trước tuning và giữ tỷ lệ nhãn/ngôn ngữ
   đủ đại diện ở từng split.
5. Train artifact đơn ngữ riêng bằng `--language vi` hoặc `--language en`.
   Không trộn `mixed` vào model đơn ngữ. Chỉ thêm adapter multilingual sau khi có
   tập `mixed` đủ lớn, protocol đánh giá và artifact riêng.

Khởi đầu thực tế nên là corpus `vi` có consent để chứng minh pipeline và benchmark
model tiếng Việt. Đồng thời thu thập `en`/`mixed` ở dạng có nhãn ngôn ngữ để đo
coverage, nhưng giữ chúng ở `unknown` cho tới khi model tương ứng được đánh giá.

## 6. Truy xuất online và offline

- Dashboard đọc online qua REST; SSE chỉ thông báo có thay đổi. Evidence hiển thị
  language route và lý do `unknown`.
- `GET /v1/meetings/{meeting_id}/analytics/evidence-manifest?run_id=<uuid>` tạo
  manifest audit đã redaction: run/version/fingerprint, segment ID, route, nhãn và
  lý do abstain; không trả raw transcript hoặc tên speaker trong manifest.
- Backup offline là PostgreSQL backup đã mã hóa và restore drill theo runbook, không
  phải browser cache của raw transcript.

## 7. Giới hạn hiện tại

Runtime `rules` và `tfidf-logreg` không tự trở thành model song ngữ. Rules chỉ hỗ
trợ `vi`; TF-IDF chỉ suy luận cho `supported_languages` được đóng gói trong artifact.
`mixed` luôn abstain an toàn cho đến khi có model multilingual đã được đánh giá.
