# EDA — UIT-VSMEC polarity proxy

> Trạng thái: EDA cho smoke test của pipeline PhoBERT. Đây không phải EDA cho
> corpus transcript cuộc họp và không được dùng làm kết quả cuối của Chương 8.

## 1. Phạm vi và cách tái lập

Dataset được tạo bởi
[`build_uit_vsmec_proxy.py`](../../source/model-data/tools/build_uit_vsmec_proxy.py)
từ ba split UIT-VSMEC. Emotion được map về polarity như sau:

| Polarity | Emotion nguồn |
| --- | --- |
| `negative` | Anger, Disgust, Fear, Sadness |
| `neutral` | Other |
| `positive` | Enjoyment |

`Surprise` bị loại, vì không thể kết luận là tích cực hay trung tính chỉ từ nhãn
emotion. Builder chuẩn hoá whitespace, giữ nguyên partition nguồn và loại
exact-text trùng trong/cross split. EDA không xuất text mẫu, speaker hay nội dung
transcript.

```bash
.venv/bin/python source/model-data/tools/eda_sentiment_dataset.py \
  --train source/model-data/work/uit-vsmec-polarity-proxy-v1/train.csv \
  --validation source/model-data/work/uit-vsmec-polarity-proxy-v1/validation.csv \
  --test source/model-data/work/uit-vsmec-polarity-proxy-v1/test.csv \
  --dataset-manifest source/model-data/work/uit-vsmec-polarity-proxy-v1/dataset-manifest.json \
  --dataset-version uit-vsmec-polarity-proxy-v1 \
  --dataset-profile proxy-smoke \
  --output-dir source/model-data/work/uit-vsmec-polarity-proxy-v1 \
  --dataset-name uit-vsmec-polarity-proxy-v1 \
  --group-id-meaning 'Synthetic per-row proxy ID; not a meeting ID' \
  --limitation 'External social-media emotion corpus, not consented meeting transcript data.' \
  --limitation 'Emotion labels were mapped to polarity; Surprise was excluded as ambiguous.' \
  --limitation 'Synthetic per-row IDs cannot support meeting-level generalization or leakage claims.' \
  --overwrite
```

Lệnh chạy quality gate trước, rồi tạo `quality-report.json`, `eda-summary.json`
và `eda-report.md` trong output directory. Hai file local này không nên commit
cùng data.

## 2. Kích thước và phân bố split

| Split | Số mẫu | ID nhóm duy nhất | Exact duplicate trong split | Median token | P95 token |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 5.302 | 5.302 | 0 | 12 | 33 |
| Validation | 656 | 656 | 0 | 12 | 31 |
| Test | 655 | 655 | 0 | 12 | 31 |
| **Tổng** | **6.613** | — | **0** | **12** | **33** |

`token` ở bảng trên là token tách bằng whitespace chỉ phục vụ EDA. PhoBERT sử
dụng word segmentation và tokenizer riêng; cần đo tỷ lệ truncation sau tokenization.

## 3. Phân bố nhãn

| Nhãn | Số mẫu | Tỷ lệ |
| --- | ---: | ---: |
| `negative` | 3.358 | 50,78% |
| `neutral` | 1.290 | 19,51% |
| `positive` | 1.965 | 29,71% |

`negative` nhiều hơn `neutral` khoảng 2,60 lần. Vì vậy accuracy đơn thuần có thể
che giấu lỗi trên `neutral`; đánh giá phải báo cáo macro-F1, F1 từng nhãn và
confusion matrix. Cả validation và test đều có ba nhãn, nhưng threshold/temperature
chỉ được chọn từ validation.

## 4. Độ dài văn bản

| Đo lường toàn bộ dataset | Ký tự | Token whitespace |
| --- | ---: | ---: |
| Min | 4 | 1 |
| Mean | 56,87 | 14,23 |
| Median | 48 | 12 |
| P95 | 129 | 33 |
| Max | 640 | 164 |

`max_length=256` là baseline hợp lý để benchmark, nhưng không phải bằng chứng rằng
không có truncation: số subword PhoBERT có thể lớn hơn số token whitespace. Hãy lưu
tỷ lệ mẫu bị truncate trong evaluation thật.

## 5. Kiểm tra chất lượng split

| Kiểm tra | Kết quả |
| --- | ---: |
| Text rỗng | 0 |
| Exact text trùng train / validation | 0 |
| Exact text trùng train / test | 0 |
| Exact text trùng validation / test | 0 |
| Text đã chuẩn hoá, duy nhất | 6.613 / 6.613 |

Các kết quả xác nhận builder và validator làm việc đúng cho smoke test. Chúng không
xác nhận khả năng tổng quát theo meeting, vì mỗi `meeting_id` trong proxy là ID
synthetic cho một dòng; không có quan hệ meeting/speaker thật để kiểm tra.

## 6. Kết luận sử dụng

Proxy phù hợp để kiểm tra schema, split validator, word segmentation, fine-tune,
calibration và packaging artifact. Nó không phù hợp để báo cáo chất lượng sentiment
Google Meet/Vexa, chọn model production, chứng minh chống leakage theo meeting,
hoặc thay thế corpus họp đã consent, double annotation và adjudication.

Khi có corpus thật, chạy lại cùng script EDA với `meeting_id` thật, bổ sung thống
kê số meeting/speaker/unit, phân bố theo meeting, annotation agreement, tỷ lệ
quality gate/retraction và error slice theo use case.
