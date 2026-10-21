# Kho bằng chứng kiểm chứng thực nghiệm

Thư mục này lưu artifact sinh ra từ các run thật cho Chương 8. Không dùng nó để tạo số liệu ước lượng hoặc lưu transcript/secret thật.

## Công cụ cần có

| Mục đích | Công cụ | Lệnh kiểm tra |
|---|---|---|
| Unit/contract test | `uv`, `pytest` | `cd source/src/backend && uv run pytest -q` |
| Lint | `ruff` | `uv run ruff check app tests` |
| Runtime MVP | Docker Engine + Compose v2 | `docker compose version` |
| API/readiness | `curl`, `python3` | `curl --version` |
| Log/commit | `git` | `git rev-parse HEAD` |
| PDF luận văn | `latexmk` | `latexmk -pdf main.tex` |
| Vexa E2E (tùy chọn) | Vexa self-host + HTTPS webhook | xem `source/README.md` |

## Cấu trúc một evidence bundle

Mỗi run tạo đúng một thư mục `runs/EVID-YYYYMMDD-XXX/` từ template:

```text
runs/EVID-YYYYMMDD-XXX/
├── manifest.md
├── commands.txt
├── stdout.log
├── environment.txt
└── api-result.redacted.json   # chỉ fixture synthetic
```

Không commit thư mục run nếu chưa redaction và chưa được duyệt. Không lưu `settings.env`, API key, HMAC secret, consent form hay transcript/định danh thật trong repository.

## Quy trình kiểm chứng Chương 8

1. Chạy `../scripts/capture-evidence.sh unit EVID-YYYYMMDD-UT01` để tạo bundle và chạy unit test.
2. Kiểm tra `stdout.log`; chỉ ghi `PASS` khi exit code bằng 0.
3. Chuẩn bị `source/settings.env` cục bộ, rồi chạy `../scripts/capture-evidence.sh integration EVID-YYYYMMDD-INT01` để kiểm chứng API → PostgreSQL → Valkey → worker → analytics.
4. Lặp integration tối thiểu 10 lần nếu cần báo success rate; mỗi lần dùng Evidence ID riêng.
5. Đổi `CLASSIFIER_ADAPTER=dummy-contract` và `MODEL_VERSION=dummy-contract-v1`, chạy lại integration để kiểm chứng RQ2. Khôi phục hai biến về `rules`/`baseline-rules-v2` sau run.
6. Chỉ thực hiện Vexa/Google Meet E2E sau consent và HTTPS webhook; ghi loại dữ liệu là `real-consented`, redaction log/screenshot trước khi lưu.
7. Điền số liệu từ bundle vào Chương 8: ID, commit, môi trường, command, số run, pass/fail, giới hạn. Không suy diễn F1, ASR WER hay SLA từ fixture synthetic.

## Ý nghĩa claim

- Unit test: xác nhận invariant code, không đo chất lượng sentiment.
- Integration synthetic: xác nhận pipeline nội bộ, không phải accuracy/F1 hoặc Vexa E2E.
- Adapter swap: xác nhận RQ2 tại boundary kiến trúc, không chứng minh PhoBERT.
- Vexa E2E có consent: xác nhận tích hợp vận hành, không là benchmark ASR/model.
