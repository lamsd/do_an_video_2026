# BÁO CÁO ĐÁNH GIÁ VÀ PHẢN BIỆN KHÓA LUẬN TỐT NGHIỆP

**Tên đề tài:** Hệ thống phân tích sắc thái cảm xúc từ transcript tiếng Việt trong họp trực tuyến  
**Ngành:** Khoa học Máy tính — Mã ngành: 8480101  
**Đơn vị:** Khoa Công nghệ Thông tin — Trường Đại học Giao thông Vận tải TP. Hồ Chí Minh  
**Giảng viên hướng dẫn:** TS. Đặng Nhân Cách  
**Vai trò người đánh giá:** Chuyên gia / Giáo sư Phản biện Học thuật  

---

## 1. TỔNG QUAN VÀ ĐÁNH GIÁ CHUNG (EXECUTIVE SUMMARY)

Khóa luận tốt nghiệp xây dựng một ứng dụng sản phẩm khả dụng tối thiểu (MVP) nhằm xử lý và phân tích sắc thái cảm xúc (sentiment analysis) từ văn bản chép lời (transcript) tiếng Việt trong các cuộc họp trực tuyến (Google Meet thông qua Vexa). Tác giả tiếp cận bài toán dưới góc độ **Khoa học Thiết kế trong Hệ thống Thông tin (Design Science Research)**, tập trung vào việc xây dựng một đường đi dữ liệu có thể truy vết (evidence traceability), đảm bảo quyền riêng tư (privacy by design) và cập nhật gần thời gian thực (near-real-time).

### Điểm sáng nổi bật của Khóa luận:
1. **Tư duy Kiến trúc Hệ thống bài bản:** Tác giả thể hiện năng lực thiết kế phần mềm tốt. Việc tách biệt các tầng (FastAPI backend, Worker xử lý bất đồng bộ qua Valkey Stream, PostgreSQL lưu trữ chuẩn, SSE push dữ liệu lên Dashboard) giúp hệ thống có tính độc lập cao.
2. **Khả năng Truy vết Dữ liệu (Provenance & Evidence):** Xây dựng thành công cơ chế lưu trữ phiên bản transcript (`revision`), phiên bản mô hình (`model_version`), phiên bản tiền xử lý (`preprocessing_version`) gắn chặt với từng `analysis_unit`.
3. **Ranh giới Đạo đức và Bảo mật rõ ràng:** Nhận thức rất sâu sắc về bảo vệ dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP, GDPR) và phân định ranh giới khoa học: **tuyệt đối không đồng nhất sentiment ngôn ngữ với chẩn đoán sức khỏe tâm thần/trầm cảm (PHQ-9, DSM-5)**.

Tuy nhiên, khóa luận tồn tại một số **hạn chế cốt lõi về mặt thực nghiệm và nội dung** cần được điều chỉnh gấp trước khi đưa ra Hội đồng bảo vệ.

---

## 2. DANH MỤC LỖI HÌNH THỨC VÀ CHỖ CHƯA HOÀN THIỆN (FORMAL ERRORS & PLACEHOLDERS)

| STT | Vị trí / Mục | Mô tả lỗi / Chỗ chưa hoàn thiện | Hướng khắc phục |
| :--- | :--- | :--- | :--- |
| **1** | Trang bìa & Lời cam đoan | Còn nguyên các thẻ Placeholder chưa điền thông tin: `[CẦN ĐIỀN: Họ và tên sinh viên]`, `[CẦN ĐIỀN: MSSV]`, `[CẦN ĐIỀN: Tên lớp]`, `[CẦN ĐIỀN: tháng/năm]`. | Điền đầy đủ thông tin cá nhân, mã số sinh viên, lớp và thời gian hoàn thành chính thức. |
| **2** | Tóm tắt & Abstract | Tác giả thừa nhận không công bố các giá trị định lượng về độ trễ, WER ASR, coverage hay chất lượng sentiment. | Cần điều chỉnh câu từ để khẳng định đây là nghiên cứu định hướng kiến trúc MVP, tránh gây cảm giác bài báo/luận văn bị nộp thiếu. |
| **3** | Chương 8 (Các bảng thực nghiệm) | Bảng 8.2 (Báo cáo so sánh model) và Bảng 8.3 (Mẫu bằng chứng integration) để trống các ô giá trị ("chưa đo"). | Cần ghi rõ trong chú thích bảng là "Khung biểu mẫu thực nghiệm đề xuất cho các nghiên cứu tiếp theo". |

---

## 3. ĐÁNH GIÁ PHẢN BIỆN NỘI DUNG VÀ PHƯƠNG PHÁP LUẬN (CRITICAL REVIEW)

### 3.1 Khoảng trống Thực nghiệm AI/NLP (Empirical Gap)
- **Vấn đề:** Đề tài mang tên *"Hệ thống phân tích sắc thái cảm xúc..."* thuộc ngành Khoa học Máy tính, nhưng runtime thực tế được kiểm chứng trong MVP chỉ là **`baseline-rules-v2`** (bộ luật gán nhãn dựa trên từ khóa tích cực/tiêu cực). Khóa luận **hoàn toàn chưa fine-tune, benchmark hoặc serving mô hình PhoBERT hay Custom Model học máy nào**.
- **Phản biện:** Việc chỉ chạy kiểm thử luồng bằng Rule Baseline làm giảm đáng kể hàm lượng khoa học về mặt NLP/AI của một khóa luận Khoa học Máy tính. Bài luận dành nhiều trang viết về PhoBERT, mBERT, Transformer, MLflow, nhưng đó mới chỉ dừng ở mức "nghiên cứu lý thuyết" và "thiết kế đề xuất".

### 3.2 Sự Mâu thuẫn giữa Tên Đề tài và Phạm vi Hiện thực
- **Vấn đề:** Tên đề tài dễ tạo kỳ vọng cho người đọc/Hội đồng về một hệ thống AI phân tích cảm xúc hoàn chỉnh với độ chính xác cao. Tuy nhiên, sản phẩm thực tế là một **khung hạ tầng kỹ thuật phần mềm (Software Infrastructure MVP)** để tích hợp mô hình.
- **Phản biện:** Nếu Hội đồng tập trung xoáy sâu vào độ chính xác (Accuracy, Macro-F1, Confusion Matrix) của mô hình phân tích cảm xúc tiếng Việt, tác giả sẽ bị rơi vào thế bị động vì chưa có dữ liệu gán nhãn thực tế trên miền cuộc họp.

### 3.3 Sự Hiện diện của Notebook Phân loại Trầm cảm trong Codebase
- **Vấn đề:** Trong Chương 1.4 và 4.1, tác giả có giải thích rằng các notebook sẵn có trong dự án thuộc bài toán *"phân loại trầm cảm nhị phân"* và không thuộc phạm vi MVP.
- **Phản biện:** Sự xuất hiện của các file này trong repository dự án dễ gây nhầm lẫn nghiêm trọng về mục tiêu nghiên cứu và tạo ra rủi ro đạo đức nếu Hội đồng nghi ngờ tác giả dùng sai bài toán hoặc "râu ông nọ chắp cằm bà nhơ".

### 3.4 Độ Phụ thuộc Hạ tầng và Tính Khả thi
- **Vấn đề:** Hệ thống phụ thuộc hoàn toàn vào dịch vụ bên thứ ba **Vexa** để thu thập transcript từ Google Meet. Tích hợp Zoom, Microsoft Teams, Jitsi Meet mới dừng lại ở sơ đồ thiết kế nét đứt.
- **Phản biện:** Rủi ro vận hành xảy ra khi Vexa thay đổi cấu trúc Webhook hoặc API. Ngoài ra, việc dùng header `X-App-User-Id` cho định danh người dùng là cơ chế phát triển (dev-only), chưa có Authentication/Authorization chuẩn sản xuất (OAuth2/JWT/RBAC).

---

## 4. GỢI Ý CHỈNH SỬA CHI TIẾT (ACTIONABLE REVISION ROADMAP)

### Phase 1: Chỉnh sửa Khẩn cấp trước khi In / Bảo vệ (Nhiệm vụ bắt buộc)
1. **Rà soát toàn bộ Text Placeholder:** Điền ngay thông tin Sinh viên, MSSV, Lớp, Ngày tháng tại Trang bìa, Lời cam đoan và Lời cảm ơn.
2. **Làm rõ Phạm vi Đóng góp ngay từ Lời Giới Thiệu & Tóm Tắt:** 
   - Khẳng định rõ: *"Đóng góp cốt lõi của khóa luận là Kiến trúc Hệ thống có thể kiểm toán (Auditable Architecture MVP) và Hợp đồng Adapter tích hợp mô hình, không phải là một mô hình PhoBERT đã fine-tune."*
3. **Bổ sung Chú thích Rõ ràng cho các Bảng mẫu ở Chương 8:**
   - Tại Bảng 8.2 và 8.3, bổ sung ghi chú: *"Bảng đóng vai trò là protocol và template chuẩn bị cho quá trình huấn luyện/đánh giá mô hình khi có corpus transcript họp gán nhãn."*
4. **Loại bỏ hoặc Đóng gói Tách biệt các Notebook Trầm cảm:**
   - Di chuyển các notebook phân loại trầm cảm ra khỏi thư mục chính của dự án MVP để tránh bị bắt lỗi sai lệch miền bài toán.

### Phase 2: Chuẩn bị Kịch bản Phản biện trước Hội đồng (Defense Q&A Strategy)

* **Câu hỏi 1:** *"Tại sao khóa luận Khoa học Máy tính về Phân tích Cảm xúc lại không có kết quả F1-Score hay Accuracy của PhoBERT?"*
  * **Cách trả lời khuyến nghị:** Báo cáo rõ ràng rằng đề tài tiếp cận theo hướng Design Science Research. Trong bối cảnh chưa có dataset transcript họp tiếng Việt chuẩn được gán nhãn đúng task 3 lớp, việc ép fine-tune trên dữ liệu out-of-domain (như mạng xã hội) sẽ dẫn đến kết quả sai lệch. Do đó, nghiên cứu tập trung giải quyết bài toán khó hơn là **xây dựng hạ tầng đường ống dữ liệu, adapter và kiểm soát đạo đức/truy vết**, sẵn sàng cho việc cắm (plug-and-play) mô hình PhoBERT khi có dữ liệu gán nhãn chuẩn.

* **Câu hỏi 2:** *"Hệ thống này có thể dùng để đánh giá hiệu suất làm việc hoặc mức độ hài lòng của nhân viên trong công ty không?"*
  * **Cách trả lời khuyến nghị:** Nhấn mạnh ranh giới đạo đức đã nêu ở Chương 9. Output sentiment chỉ mô tả sắc thái của đoạn văn bản (analysis unit) trong ngữ cảnh hẹp, không phản ánh năng lực, tâm lý hay thái độ lâu dài của cá nhân. Hệ thống được thiết kế để hỗ trợ quan sát tổng thể cuộc họp với sự giám sát của con người (Human-in-the-loop).

---

## 5. KẾT LUẬN ĐÁNH GIÁ

Khóa luận được trình bày **rất ngăn nắp, tính logic cao, văn phong học thuật chuẩn mực** và thể hiện năng lực chuyên môn xuất sắc về **Kỹ thuật Phần mềm và Kiến trúc Hệ thống**. Mặc dù có hạn chế lớn về mặt thực nghiệm AI/NLP định lượng, tác giả đã rất thành thật và minh bạch khi chỉ rõ các giới hạn này trong luận văn.

**Đánh giá tổng thể:** Đủ điều kiện đưa ra bảo vệ trước Hội đồng sau khi đã hoàn thiện các lỗi hình thức (placeholder) và đính chính rõ ràng phạm vi đóng góp.
