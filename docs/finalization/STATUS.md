# Trạng thái hoàn thiện khóa luận

Cập nhật: 2026-11-16. Trạng thái này mô tả đúng evidence đang có trong repository,
không thay thế cho buổi Jitsi có người tham gia và consent.

| Hạng mục | Trạng thái | Bằng chứng / việc còn lại |
|---|---|---|
| Contract model runtime | DONE | Default và adapter đều là `baseline-rules-v3`; `unknown` là abstention. |
| Quality gate và unit cùng speaker | DONE | Unit tests trong backend pass. |
| Queue durable/recovery | DONE (code + unit) | Worker reclaim Valkey pending message sau idle lease; `queued` scanner vẫn là fallback. Chưa cố ý kill worker trong stack thật. |
| API/DB/UI cùng run/revision | DONE (synthetic API) | Snapshot, revision, model/preprocessing và redacted manifest được kiểm bằng fixture. Dashboard visual UAT còn cần người vận hành. |
| Idempotency, late revision/retraction, cross-meeting access, SSE reconnect | DONE (synthetic) | `smoke-analysis-pipeline.sh` kiểm fixture PostgreSQL/Valkey/worker thực và tự xóa dữ liệu. |
| Worker restart/queue recovery | DONE (unit) | Test reclaim mô phỏng pending message; cần forced-restart evidence riêng nếu muốn claim operational. |
| Jitsi E2E 2 người + 1 bot | NOT RUN | Thực hiện theo `docs/operations/JITSI_E2E_VERIFICATION_CHECKLIST.md`, chỉ sau consent. |
| WER/CER, F1, kappa, P50/P95 | BLOCKED | Chưa có tập tham chiếu/nhãn độc lập được phép commit; evaluator active-runtime là Phase 2, chưa triển khai. |
| A0/A1/A2 đối chứng | BLOCKED | Cần cùng một tập nhãn cố định, không hiệu chỉnh rule trên tập test. |
| Luận văn/README | DONE (tài liệu) | Nội dung phải tiếp tục phản ánh các mục NOT RUN/BLOCKED ở trên. |

## Lệnh kiểm chứng đã chạy

```bash
cd source/src/backend
.venv/bin/python -m pytest -q
.venv/bin/ruff check app tests
cd ../..
./scripts/verify.sh
./scripts/smoke-analysis-pipeline.sh
```

Kết quả: `46 passed`; Ruff không lỗi; smoke synthetic pass sau khi rebuild
`backend` và `worker`. Fixture không phải evidence Jitsi hoặc kết quả nghiên cứu.
Chi tiết tại [TEST_REPORT.md](TEST_REPORT.md) và [EVALUATION_REPORT.md](EVALUATION_REPORT.md).

## Điều kiện nghiệm thu còn thiếu

1. Có consent và chạy Jitsi thật với 2 người + 1 bot; lưu manifest đã redaction,
   API/DB/UI snapshot của đúng meeting/run/revision.
2. Hai người gán nhãn độc lập trên tập transcript cố định; mới tính WER/CER, F1,
   confusion matrix và Cohen's kappa.
3. Chạy evidence bundle v3, forced-restart và E2E thật khi đủ điều kiện.
