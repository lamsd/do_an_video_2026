# Rà soát dữ liệu trước huấn luyện — `tram_cam`

**Ngày rà soát:** 18-10-2026  
**Phạm vi:**
[`final_cleaned_dataset.csv`](../../Reports/New_folder/tram_cam/final_cleaned_dataset.csv)
và
[`phobert_ready_dataset.csv`](../../Reports/New_folder/tram_cam/phobert_ready_dataset.csv).

## Kết luận quyết định

Hai tệp đã chứa tiếng Việt trong cột `text_vi`; **không thực hiện dịch máy hay
ghi đè dữ liệu nguồn**. Dịch lại có thể thay đổi sắc thái, phủ định và ý nghĩa
của nhãn nhị phân mà hiện chưa có định nghĩa nhãn được lưu kèm trong hai CSV.

Hai tệp cũng **không được ghép với nhau để train**. Có 3.782 văn bản trùng nhau
sau chuẩn hoá khoảng trắng/chữ hoa-thường, và chúng đều mang nhãn `1` ở cả hai
tệp. Ghép trực tiếp sẽ lặp dữ liệu, làm lệch phân bố nhãn và có thể gây leakage
khi chia train/validation/test.

Quan trọng hơn, đây là dữ liệu thuộc thư mục `tram_cam`, nhị phân, không có
`meeting_id` và không có ba nhãn polarity. Nó **không phù hợp và không được dùng
cho `MeetingSentiment-PhoBERT` hay dashboard phân tích cuộc họp**. Phân loại
sentiment của nội dung cuộc họp không phải là sàng lọc hay suy luận trạng thái
sức khoẻ tâm thần của một người.

## 1. Ảnh chụp kỹ thuật của dữ liệu

Các số liệu dưới đây được tính trực tiếp từ tệp CSV, không đưa câu văn nguồn vào
báo cáo vì nội dung có thể nhạy cảm.

| Thuộc tính | `final_cleaned_dataset.csv` | `phobert_ready_dataset.csv` |
| --- | ---: | ---: |
| SHA-256 | `88161f9388194bbb9cede048223d8f7f6bc6ab68670c373eeffd13bbb45de842` | `73ff270cc33ad71cb56c8c4536123f7f8fba244cc52b7d72ec696c8f477b00a3` |
| Số dòng dữ liệu | 7.345 | 5.933 |
| Cột | `text_vi`, `sentiment` | `text_vi`, `sentiment`, `text_clean` |
| Nhãn `0` / `1` | 3.563 / 3.782 | 2.151 / 3.782 |
| Văn bản rỗng | 0 | 0 |
| Nhãn ngoài `0`, `1` | 0 | 0 |
| Bản ghi trùng trong chính tệp | 0 | 0 |
| Có dấu hiệu ký tự tiếng Việt | 7.319 (99,65%) | 5.888 (99,24%) |
| Độ dài `text_vi` trung vị / P95 (ký tự) | 89 / 1.688 | 355 / 2.607 |
| Dài hơn 512 / 2.000 ký tự | 1.625 / 248 | 2.296 / 475 |

`text_clean` không rỗng ở toàn bộ 5.933 dòng, nhưng khác `text_vi` ở 5.788 dòng.
Nó là biến thể đã tiền xử lý, không phải một nguồn dữ liệu độc lập.

26 dòng ở tệp thứ nhất và 45 dòng ở tệp thứ hai không có ký tự dấu tiếng Việt.
Con số này chỉ là tín hiệu kiểm tra ngôn ngữ (câu ngắn, số, URL hoặc văn bản không
dấu cũng có thể tạo ra kết quả đó); cần gắn cờ để rà soát, **không tự động dịch**.

## 2. Quan hệ giữa hai tệp

So sánh theo `text_vi` sau khi bỏ khoảng trắng dư và không phân biệt hoa/thường:

| Chỉ số đối chiếu | Kết quả |
| --- | ---: |
| Văn bản giao nhau | 3.782 |
| Tỷ lệ của `final_cleaned_dataset.csv` | 51,49% |
| Tỷ lệ của `phobert_ready_dataset.csv` | 63,75% |
| Nhãn nhất quán trong phần giao | 3.782/3.782 (100%) |
| Nhãn của phần giao | toàn bộ là `1` |

Vì vậy, hai CSV chỉ có thể được xem là hai bản dẫn xuất/corpus có quan hệ, chứ
không phải hai tập độc lập để cộng dồn. Đặc biệt, việc nối hai tệp sẽ tạo 13.278
dòng nhưng chỉ có 9.496 văn bản duy nhất; 3.782 dòng lặp đều thuộc một nhãn.

## 3. Các điểm chặn trước khi huấn luyện

1. **Không có ánh xạ ý nghĩa nhãn.** `0` và `1` là mã kỹ thuật; không được tự
   gọi là `negative`/`positive`, “có/không có trầm cảm”, hay bất kỳ diễn giải
   nào khác khi chưa có nguồn gốc, guideline gán nhãn và phê duyệt chuyên môn.
2. **Không có dữ liệu provenance trong CSV.** Hai tệp không chứa nguồn gốc,
   giấy phép, consent, thời điểm thu thập, chính sách redaction, annotator hay
   phạm vi sử dụng. Cần xác minh các thông tin này trước mọi thí nghiệm nhị phân
   riêng biệt.
3. **Không có split và group ID.** Chưa có `train.csv`, `validation.csv`,
   `test.csv` bất biến; cũng không có ID nhóm để ngăn leakage giữa các split.
4. **Nhiều văn bản dài.** Với PhoBERT, giới hạn token sẽ cắt bớt nội dung; không
   được chỉ cắt theo số ký tự. Phải chọn policy segment/chunk trước, áp dụng như
   nhau cho train, validation và test, rồi ghi vào manifest.
5. **Ngữ cảnh và nhiệm vụ không khớp hệ thống.** Tập nhị phân này không có ngữ
   cảnh transcript cuộc họp, `meeting_id`, hay nhãn `negative`/`neutral`/
   `positive` mà pipeline dự án yêu cầu.

## 4. Quyết định sử dụng

| Mục đích | Quyết định |
| --- | --- |
| Fine-tune `MeetingSentiment-PhoBERT` | **Không dùng** hai tệp này. |
| Đánh giá/chứng minh chất lượng sentiment của hệ thống họp | **Không dùng**. Khác domain, khác schema nhãn và thiếu split theo meeting. |
| Ghép hai tệp thành một CSV | **Không làm** vì đã xác nhận trùng 3.782 văn bản. |
| Dịch sang tiếng Việt | **Không làm**; `text_vi` đã là văn bản tiếng Việt. Rà soát thủ công các dòng bị gắn cờ ngôn ngữ nếu cần cho một nghiên cứu đã được phê duyệt. |
| Thí nghiệm nhị phân độc lập ngoài phạm vi dự án | Chỉ cân nhắc sau khi có data card, nguồn/license/consent, định nghĩa nhãn, đánh giá rủi ro và phê duyệt phù hợp. Không đưa dữ liệu hay artifact đó vào runtime dashboard. |

Nếu cần kiểm tra cơ chế PhoBERT/Colab trước khi có corpus họp được phê duyệt,
hãy dùng proxy UIT-VSMEC đã được gắn nhãn là smoke test; không dùng `tram_cam`
để thay thế. Xem [EDA proxy UIT-VSMEC](EDA_UIT_VSMEC_PROXY.md).

## 5. Bộ dữ liệu đúng cho lần train tiếp theo

Corpus cho dự án cần nằm ngoài Git tại:

```text
source/model-data/approved/<dataset-version>/
  train.csv
  validation.csv
  test.csv
```

Mỗi tệp phải có tối thiểu:

```csv
text,label,meeting_id
"Nội dung transcript đã redaction",neutral,meeting-001
```

- `label` chỉ nhận `negative`, `neutral`, `positive`.
- Chia split theo `meeting_id` **trước** tuning; một meeting không được xuất hiện
  ở hai split.
- Lưu manifest: version và SHA-256 từng split, nguồn/consent/license, số
  meeting/speaker/unit, thời gian thu thập, rule redaction, guideline nhãn,
  annotator, adjudication và lý do loại dữ liệu.
- Hai annotator gán nhãn độc lập, xử lý bất đồng và báo cáo agreement.
- Khoá test set; chỉ dùng validation để chọn epoch, threshold và các siêu tham số.

Đặc tả đầy đủ nằm tại
[Custom model cho Meeting Intelligence](CUSTOM_MODEL_MEETING_SENTIMENT.md#4-dữ-liệu-đúng-task).
Trainer cũng kiểm tra schema, nhãn và leakage theo `meeting_id`/văn bản:
[train_meeting_sentiment_phobert.py](../../source/model-data/colab/train_meeting_sentiment_phobert.py).
Chạy quality gate độc lập trước EDA/train bằng
[check_meeting_dataset_quality.py](../../source/model-data/tools/check_meeting_dataset_quality.py);
report chỉ chứa số liệu tổng hợp và hash.

## 6. Checklist trước khi bấm Train

- [ ] Xác nhận bài toán là sentiment transcript cuộc họp, không phải phân loại
      sức khoẻ tâm thần.
- [ ] Có corpus đã consent/license, redaction và manifest hoàn chỉnh.
- [ ] Có ba nhãn polarity cùng guideline và kết quả adjudication.
- [ ] Chia theo `meeting_id`; kiểm tra leakage và khoá test set.
- [ ] Chạy quality gate, xác nhận manifest/hash khớp và lưu `quality-report.json`.
- [ ] Chốt policy xử lý đoạn dài và phiên bản word segmentation/tokenizer.
- [ ] Chạy `--validate-only` trên ba split trước khi tải model hoặc tạo artifact.
- [ ] Huấn luyện trên Colab, lưu metrics, confusion matrix, calibration,
      threshold, hash dữ liệu và model card.

Khi toàn bộ checklist đạt, dùng notebook
[MeetingSentiment_PhoBERT_Training_Colab.ipynb](../../source/model-data/colab/MeetingSentiment_PhoBERT_Training_Colab.ipynb)
hoặc trainer tương ứng. Trước thời điểm đó, hai CSV trong tài liệu này chỉ được
giữ làm dữ liệu tham khảo bị cách ly khỏi pipeline meeting sentiment.

