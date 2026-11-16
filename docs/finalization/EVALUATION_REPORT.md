# Evaluation report

`source/meeting-intelligence-backend/tools/evaluate_sentiment.py` đọc CSV với các
cột `unit_id,gold_label,predicted_label,accepted`. Gold label chỉ nhận
`positive`, `neutral`, `negative`; prediction `unknown` là abstention.

```bash
cd source/meeting-intelligence-backend
.venv/bin/python tools/evaluate_sentiment.py labelled.csv --output evidence/metrics.json
```

Báo cáo JSON có A/T (segment acceptance), P/A (prediction coverage), P/T,
accuracy, macro-F1 trên toàn tập có nhãn (abstention là miss), macro-F1 chỉ trên
phần có prediction, per-class metric và confusion matrix. Coverage không được
diễn giải là accuracy.

`sentiment_labels.example.csv` là dữ liệu giả tối thiểu để smoke-test parser; số
liệu của nó không được chép vào luận văn. Hiện repository không có transcript
tham chiếu/nhãn độc lập đủ consent để tính WER/CER, F1 nghiên cứu, kappa, A0/A1/A2
hay P50/P95. Các chỉ số đó là **NOT RUN/BLOCKED**, không phải zero.
