# Audit UIT-VSMEC trong phạm vi nghiên cứu legacy

## Trạng thái

**QUARANTINE — chưa tạo corpus train/validation/test dẫn xuất.** Dữ liệu không được đưa vào `source/model-data/approved/meeting-sentiment-pilot-v1`, không gộp vào corpus nhị phân `tram_cam`, và không dùng cho model, API, dashboard hoặc pilot cuộc họp.

Lý do: nguồn có bài toán cảm xúc đa lớp khác với sentiment nhị phân, một nội dung trùng giữa train và validation, và một nội dung có nhãn mâu thuẫn trong train. Tự động sửa hoặc bỏ các dòng này sẽ thay đổi split/nhãn do nguồn cung cấp, nên cần quyết định nghiên cứu có ghi nhận.

## Nguồn đã kiểm kê

| Split nguồn | Tệp | Số dòng | Cột dùng |
|---|---:|---:|---|
| Train | `train_nor_811.xlsx` | 5.548 | `Sentence`, `Emotion` |
| Validation | `valid_nor_811.xlsx` | 686 | `Sentence`, `Emotion` |
| Test | `test_nor_811.xlsx` | 693 | `Sentence`, `Emotion` |
| Tổng |  | 6.927 |  |

Mỗi workbook có một cột Excel không đặt tên nhưng chứa dữ liệu trên toàn bộ dòng. Công cụ không suy đoán ý nghĩa cột đó và không dùng nó làm input model. Schema đầy đủ, hash SHA-256 của mỗi file và số ô bỏ qua sẽ được lưu trong manifest nếu corpus được phép tạo.

## Nhãn nguồn giữ nguyên

| Source label | Tổng số dòng |
|---|---:|
| Anger | 480 |
| Disgust | 1.338 |
| Enjoyment | 1.965 |
| Fear | 395 |
| Other | 1.291 |
| Sadness | 1.149 |
| Surprise | 309 |

Đây là 7 lớp cảm xúc, không có mapping được phê duyệt sang `legacy_label` 0/1. Không được gán các lớp này thành positive/negative hoặc nhãn sức khoẻ tâm thần.

## Kiểm tra chất lượng không lộ nội dung câu

Chuẩn hoá để so sánh trùng lặp: Unicode NFKC, gộp khoảng trắng, `casefold`, rồi SHA-256. Không ghi nội dung câu vào audit.

| Kiểm tra | Kết quả |
|---|---:|
| Dòng nguồn | 6.927 |
| Nội dung duy nhất sau chuẩn hoá | 6.921 |
| Dòng trùng lặp | 6 |
| Dòng trùng trong cùng split | Train: 4; Test: 1 |
| Nội dung trùng giữa split | 1 |
| Nội dung có nhãn mâu thuẫn | 1 |

Hai collision cần xử lý theo protocol:

1. Hash `96ae1c...d2b5c4a9`: xuất hiện ở train dòng 1.032 và validation dòng 594; cả hai nhãn `Surprise`. Đây là rò rỉ train/validation.
2. Hash `c11cef...8434b164`: xuất hiện trong train ở dòng 4.118 nhãn `Disgust` và dòng 4.989 nhãn `Fear`. Đây là nhãn mâu thuẫn trong cùng nội dung.

## Điều kiện để tạo corpus dẫn xuất

Trước khi tạo `derived/uit-vsmec-multiclass-legacy-v1/`, cần chốt một chính sách có thể tái lập:

1. **Giữ nguyên nguồn:** mirror nguyên split và ghi rõ leakage/label conflict, chỉ dùng phân tích mô tả; không dùng kết quả test làm benchmark đáng tin cậy.
2. **Sanitize theo quyết định nghiên cứu:** chọn record nào giữ lại cho collision train/validation và cách xử lý hai nhãn mâu thuẫn; lưu bảng quyết định redacted và hash trước khi build.
3. **Xác minh nguồn chính thức:** kiểm tra license, citation, định nghĩa nhãn và khả năng có bản phát hành đã sửa lỗi; ưu tiên bản này thay vì tự sửa.

Chỉ sau khi chọn một chính sách, công cụ `Reports/New_folder/tram_cam/tools/build_uit_vsmec_multiclass_corpus.py` mới tạo CSV và manifest. Công cụ mặc định chặn build khi còn trùng giữa split hoặc nhãn mâu thuẫn.
