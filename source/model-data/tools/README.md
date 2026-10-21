# Dataset builders

## UIT-VSMEC polarity proxy

[`build_uit_vsmec_proxy.py`](build_uit_vsmec_proxy.py) chuyển ba partition XLSX
có sẵn của UIT-VSMEC thành `train.csv`, `validation.csv`, `test.csv` và
`dataset-manifest.json` cho **smoke test** notebook PhoBERT.

Builder giữ nguyên partition nguồn, map `Anger`, `Disgust`, `Fear`, `Sadness` về
`negative`; `Enjoyment` về `positive`; `Other` về `neutral`. `Surprise` bị loại
mặc định vì không thể map tin cậy sang polarity chỉ từ nhãn emotion. Builder cũng
loại exact-text trùng trong một split hoặc split trước để Colab validator không
dừng do leakage.

Chạy từ repository root. Output nên là thư mục tạm hoặc Drive riêng, không đặt
vào `approved/` và không commit các CSV tạo ra.

```bash
python3 source/model-data/tools/build_uit_vsmec_proxy.py \
  --train-xlsx 'Reports/New_folder/tram_cam/UIT-VSMEC/train_nor_811.xlsx' \
  --validation-xlsx 'Reports/New_folder/tram_cam/UIT-VSMEC/valid_nor_811.xlsx' \
  --test-xlsx 'Reports/New_folder/tram_cam/UIT-VSMEC/test_nor_811.xlsx' \
  --output-dir /tmp/uit-vsmec-polarity-proxy-v1 \
  --smoke-test
```

Các file CSV có schema `text,label,meeting_id` để tương thích notebook hiện tại.
`meeting_id` có prefix `proxy-vsmec-` và là ID tổng hợp theo từng dòng, **không
phải** meeting ID. Manifest ghi rõ hạn chế này. Không dùng metrics từ proxy cho
Chương 8, không nạp artifact tạo ra từ proxy vào runtime và không coi proxy là
benchmark transcript họp.

Nếu muốn thử giả định `Surprise -> neutral`, thêm
`--include-surprise-as-neutral`; đây là biến thể thí nghiệm riêng, không thay đổi
khuyến nghị mặc định.

## Quality gate và kiểm tra bằng trainer

Sau khi build, dùng môi trường `.venv` ở root dự án và chạy quality gate trước.
Lệnh tạo report tổng hợp, kiểm tra manifest/hash, schema, ba nhãn, exact-text
leakage và group leakage; không tải checkpoint hay tạo artifact.

```bash
.venv/bin/python source/model-data/tools/check_meeting_dataset_quality.py \
  --train source/model-data/work/uit-vsmec-polarity-proxy-v1/train.csv \
  --validation source/model-data/work/uit-vsmec-polarity-proxy-v1/validation.csv \
  --test source/model-data/work/uit-vsmec-polarity-proxy-v1/test.csv \
  --dataset-manifest source/model-data/work/uit-vsmec-polarity-proxy-v1/dataset-manifest.json \
  --dataset-version uit-vsmec-polarity-proxy-v1 \
  --dataset-profile proxy-smoke \
  --report source/model-data/work/uit-vsmec-polarity-proxy-v1/quality-report.json
```

Sau khi gate đạt, `--validate-only` dùng cùng contract với trainer PhoBERT. Proxy
phải khai báo tường minh và không được diễn giải là corpus meeting.

```bash
.venv/bin/python source/model-data/colab/train_meeting_sentiment_phobert.py \
  --train source/model-data/work/uit-vsmec-polarity-proxy-v1/train.csv \
  --validation source/model-data/work/uit-vsmec-polarity-proxy-v1/validation.csv \
  --test source/model-data/work/uit-vsmec-polarity-proxy-v1/test.csv \
  --dataset-manifest source/model-data/work/uit-vsmec-polarity-proxy-v1/dataset-manifest.json \
  --dataset-version uit-vsmec-polarity-proxy-v1 \
  --dataset-profile proxy-smoke \
  --acknowledge-proxy-smoke \
  --model-version phobert-proxy-smoke-v1 \
  --validate-only
```

## Bộ dữ liệu thật

Khi có transcript Vexa/Google Meet đã consent và nhãn đã adjudicate, hãy build ba
split theo `meeting_id` thật; không dùng builder proxy này. Quy trình và contract
được mô tả tại
[`docs/ai-data/CUSTOM_MODEL_MEETING_SENTIMENT.md`](../../../docs/ai-data/CUSTOM_MODEL_MEETING_SENTIMENT.md).

## EDA tái lập

[`eda_sentiment_dataset.py`](eda_sentiment_dataset.py) chạy cùng quality gate,
rồi tạo `quality-report.json`, `eda-summary.json` và `eda-report.md` chỉ từ số
liệu tổng hợp: quy mô split, nhãn, độ dài text và leakage. Script không in
content của mẫu. Kết quả EDA của proxy hiện có tại
[`docs/ai-data/EDA_UIT_VSMEC_PROXY.md`](../../../docs/ai-data/EDA_UIT_VSMEC_PROXY.md).
