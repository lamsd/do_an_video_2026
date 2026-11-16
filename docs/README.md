# Project documentation

Tài liệu được tổ chức theo vai trò. Mã nguồn và hướng dẫn chạy hiện tại nằm ở
[`../source/README.md`](../source/README.md); bằng chứng chạy được lưu riêng tại
[`../source/evidence/`](../source/evidence/).

## Bắt đầu từ đây

- [Project master guide](governance/PROJECT_MASTER_GUIDE.md): phạm vi MVP, entrypoint và quy tắc vận hành.
- [Kiến trúc runtime Jitsi - Vexa - STT](architecture/JITSI_VEXA_STT_RUNTIME_ARCHITECTURE.md): data flow, quality gate và ranh giới vận hành hiện hành.
- [Hướng dẫn build từng bước](operations/SETTINGS_AND_RUN_GUIDE.md): từ cấu hình secret, STT, Vexa, application đến smoke test và Jitsi UAT.
- [Build and acceptance runbook](operations/BUILD_AND_ACCEPTANCE_RUNBOOK.md): checkpoint nghiệm thu, phạm vi demo và evidence đã redaction.
- [Checklist Jitsi E2E](operations/JITSI_E2E_VERIFICATION_CHECKLIST.md): quy trình tạo bot, kiểm transcript và xử lý lỗi không có dữ liệu.
- [Truy xuất dữ liệu và evidence](operations/DATA_RETRIEVAL_AND_REPORTING.md): lệnh read-only cho API, logs, PostgreSQL, Valkey và số liệu báo cáo.

## Theo mục đích

| Thư mục | Nội dung |
| --- | --- |
| [`governance/`](governance/) | Phạm vi, trạng thái và chỉ mục dự án. |
| [`architecture/`](architecture/) | Thiết kế realtime, kiến trúc backend và kế hoạch triển khai. |
| [`ai-data/`](ai-data/) | Kế hoạch sentiment, quality gate, dữ liệu transcript và model roadmap. |
| [`operations/`](operations/) | Cài DEV, build/acceptance, recovery và xác minh Jitsi E2E. |
| [`deployment/`](deployment/) | Clone máy mới, UAT, portable deployment và cài Vexa. |
| [`thesis/`](thesis/) | Backlog, tổng hợp lý thuyết/triển khai và kế hoạch hoàn thiện luận văn. |
| [`presentations/`](presentations/) | Slide nguồn PPTX và PDF phát hành. |
| [`archive/`](archive/) | Tài liệu không dùng trực tiếp; hiện có bản sao Vexa trùng nội dung. |

Custom model được đặc tả tại
[Custom model cho Meeting Intelligence](ai-data/CUSTOM_MODEL_MEETING_SENTIMENT.md).
Contract dữ liệu Việt-Anh, revision snapshot và export evidence đã redaction nằm tại
[Hợp đồng dữ liệu transcript Việt-Anh](ai-data/BILINGUAL_TRANSCRIPT_DATA_CONTRACT.md).
EDA của proxy dùng để smoke test PhoBERT nằm tại
[EDA UIT-VSMEC proxy](ai-data/EDA_UIT_VSMEC_PROXY.md).
Rà soát và quyết định không dùng các CSV nhị phân trong `tram_cam` cho model họp
được ghi tại
[Rà soát dữ liệu trước huấn luyện](ai-data/PRETRAINING_DATA_REVIEW_TRAM_CAM.md).

## Quy ước trạng thái

- Runbook hiện hành: ưu tiên `governance/`, `operations/` và `deployment/`.
- Thiết kế/roadmap: `architecture/`, `ai-data/` và `thesis/` không tự chứng minh
  tính năng đã chạy; đối chiếu với mã nguồn và evidence trước khi nêu trong luận văn.
- Runtime hiện hành dùng Jitsi Meet + Vexa + STT local. PhoBERT, benchmark ASR/model,
  các platform adapter khác và production HA vẫn là hướng phát triển cho đến khi có
  evidence tương ứng.

## Lưu ý về tài liệu cũ

- [`AI_MEETING_ASSISTANT_BLUEPRINT.md`](AI_MEETING_ASSISTANT_BLUEPRINT.md) là blueprint lịch sử; dùng tài liệu kiến trúc Jitsi runtime và runbook hiện hành cho thao tác thực tế.
- [`archive/duplicates/CAI_DAT_VEXA_UBUNTU_26.04 copy.md`](archive/duplicates/CAI_DAT_VEXA_UBUNTU_26.04%20copy.md) trùng hoàn toàn với hướng dẫn Vexa chính; được giữ lại để không mất lịch sử và có thể xóa trong một commit riêng sau khi xác nhận.
