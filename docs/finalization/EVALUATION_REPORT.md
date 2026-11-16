# Evaluation report

Runtime hiện hành đã lưu A/T, P/A và P/T trong `analysis_runs.metrics`; coverage
được tách khỏi accuracy. Tuy nhiên evaluator offline cho WER/CER, F1, confusion
matrix, Cohen's kappa và P50/P95 chưa được thêm vào source runtime.

Không có transcript tham chiếu/nhãn độc lập đủ consent trong repository. Vì vậy
WER/CER, F1 nghiên cứu, kappa, A0/A1/A2 và P50/P95 đều là **NOT RUN/BLOCKED**,
không phải zero. Phase đánh giá chỉ được triển khai sau khi có schema CSV, retention
policy và tập nhãn cố định được người dùng phê duyệt.
