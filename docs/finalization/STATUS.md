# Trạng thái hoàn thiện khóa luận

Cập nhật: 2026-11-16. Trạng thái này mô tả đúng evidence đang có trong repository,
không thay thế cho buổi Jitsi có người tham gia và consent.

| Hạng mục | Trạng thái | Bằng chứng / việc còn lại |
|---|---|---|
| Contract model runtime | DONE | Default và adapter đều là `baseline-rules-v3`; `unknown` là abstention. |
| Quality gate và unit cùng speaker | DONE | Unit tests trong backend pass. |
| Queue durable/recovery | DONE (code) | `workers/sentiment.py` quét run `queued`; cần chạy stack để xác nhận operational. |
| API/DB/UI cùng run/revision | DONE (code review) | `analysis_run_id`, `source_revision`, model/preprocessing version được trả qua analytics; cần ảnh evidence runtime. |
| Idempotency, late revision/retraction, worker restart, SSE reconnect, cross-meeting access | NOT RUN | Cần integration test với PostgreSQL/Valkey và dashboard đang chạy; không suy diễn PASS từ unit test. |
| Jitsi E2E 2 người + 1 bot | NOT RUN | Thực hiện theo `docs/operations/JITSI_E2E_VERIFICATION_CHECKLIST.md`, chỉ sau consent. |
| WER/CER, F1, kappa, P50/P95 | BLOCKED | Chưa có tập tham chiếu và nhãn độc lập được phép commit; evaluator đã sẵn sàng. |
| A0/A1/A2 đối chứng | BLOCKED | Cần cùng một tập nhãn cố định, không hiệu chỉnh rule trên tập test. |
| Luận văn/README | DONE (tài liệu) | Nội dung phải tiếp tục phản ánh các mục NOT RUN/BLOCKED ở trên. |

## Lệnh kiểm chứng đã chạy

```bash
cd source/meeting-intelligence-backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests tools
.venv/bin/python tools/evaluate_sentiment.py tools/sentiment_labels.example.csv --output /tmp/sentiment-evaluation.json
```

Kết quả: `7 passed`; Ruff không lỗi. CSV example chỉ smoke-test công cụ, không phải
kết quả nghiên cứu. Chi tiết tại [TEST_REPORT.md](TEST_REPORT.md) và
[EVALUATION_REPORT.md](EVALUATION_REPORT.md).

## Điều kiện nghiệm thu còn thiếu

1. Có consent và chạy Jitsi thật với 2 người + 1 bot; lưu manifest đã redaction,
   API/DB/UI snapshot của đúng meeting/run/revision.
2. Hai người gán nhãn độc lập trên tập transcript cố định; mới tính WER/CER, F1,
   confusion matrix và Cohen's kappa.
3. Chạy integration/E2E tests và ghi exit code vào evidence bundle.
