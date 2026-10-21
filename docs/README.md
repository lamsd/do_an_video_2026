# Project documentation

Tài liệu được tổ chức theo vai trò. Mã nguồn và hướng dẫn chạy hiện tại nằm ở
[`../source/README.md`](../source/README.md); bằng chứng chạy được lưu riêng tại
[`../source/evidence/`](../source/evidence/).

## Bắt đầu từ đây

- [Project master guide](governance/PROJECT_MASTER_GUIDE.md): phạm vi MVP, entrypoint và quy tắc vận hành.
- [Build and acceptance runbook](operations/BUILD_AND_ACCEPTANCE_RUNBOOK.md): điều kiện nghiệm thu.
- [Google Meet E2E checklist](operations/GOOGLE_MEET_E2E_VERIFICATION_CHECKLIST.md): quy trình E2E có consent và bằng chứng.

## Theo mục đích

| Thư mục | Nội dung |
| --- | --- |
| [`governance/`](governance/) | Phạm vi, trạng thái và chỉ mục dự án. |
| [`architecture/`](architecture/) | Thiết kế realtime, kiến trúc backend và kế hoạch triển khai. |
| [`ai-data/`](ai-data/) | Kế hoạch sentiment, quality gate, dữ liệu transcript và model roadmap. |
| [`operations/`](operations/) | Cài DEV, build/acceptance, recovery và xác minh Google Meet E2E. |
| [`deployment/`](deployment/) | Clone máy mới, UAT, portable deployment và cài Vexa. |
| [`thesis/`](thesis/) | Backlog, tổng hợp lý thuyết/triển khai và kế hoạch hoàn thiện luận văn. |
| [`presentations/`](presentations/) | Slide nguồn PPTX và PDF phát hành. |
| [`archive/`](archive/) | Tài liệu không dùng trực tiếp; hiện có bản sao Vexa trùng nội dung. |

Custom model được đặc tả tại
[Custom model cho Meeting Intelligence](ai-data/CUSTOM_MODEL_MEETING_SENTIMENT.md).
EDA của proxy dùng để smoke test PhoBERT nằm tại
[EDA UIT-VSMEC proxy](ai-data/EDA_UIT_VSMEC_PROXY.md).
Rà soát và quyết định không dùng các CSV nhị phân trong `tram_cam` cho model họp
được ghi tại
[Rà soát dữ liệu trước huấn luyện](ai-data/PRETRAINING_DATA_REVIEW_TRAM_CAM.md).

## Quy ước trạng thái

- Runbook hiện hành: ưu tiên `governance/`, `operations/` và `deployment/`.
- Thiết kế/roadmap: `architecture/`, `ai-data/` và `thesis/` không tự chứng minh
  tính năng đã chạy; đối chiếu với mã nguồn và evidence trước khi nêu trong luận văn.
- MVP được kiểm chứng trong phạm vi Google Meet + Vexa; PhoBERT, các nền tảng họp
  khác và production HA là hướng phát triển cho đến khi có bằng chứng tương ứng.

## Lưu ý về tài liệu cũ

- [`AI_MEETING_ASSISTANT_BLUEPRINT.md`](AI_MEETING_ASSISTANT_BLUEPRINT.md) là blueprint Jitsi lịch sử, không phải runbook MVP Google Meet hiện tại.
- [`archive/duplicates/CAI_DAT_VEXA_UBUNTU_26.04 copy.md`](archive/duplicates/CAI_DAT_VEXA_UBUNTU_26.04%20copy.md) trùng hoàn toàn với hướng dẫn Vexa chính; được giữ lại để không mất lịch sử và có thể xóa trong một commit riêng sau khi xác nhận.
