# Khóa Luận LaTeX – Hướng Dẫn Sử Dụng

> Luận văn hiện chỉ claim phần ứng dụng MVP đã kiểm chứng: ingest transcript, quality gate, classifier adapter, persistence và dashboard realtime. Không dùng kết quả notebook/model khác task để claim chất lượng sentiment.

## Thông tin đề tài

**Tên đề tài**: Hệ thống phân tích sắc thái cảm xúc từ transcript tiếng Việt trong họp trực tuyến

**Người hướng dẫn**: TS. Đặng Nhân Cách

---

## Cấu trúc project

```
thesis_latex/
├── main.tex                  ← File chính, import tất cả
├── config/
│   ├── glossary.tex          ← Danh mục từ viết tắt / thuật ngữ
│   └── references.bib        ← Tài liệu tham khảo (BibTeX)
├── chapters/
│   ├── 00_cover.tex          ← Trang bìa
│   ├── 00_declaration.tex    ← Lời cam đoan
│   ├── 00_abstract.tex       ← Tóm tắt (Tiếng Việt + English)
│   ├── 00_acronyms.tex       ← Danh mục từ viết tắt
│   ├── 01_introduction.tex   ← Chương 1: Giới thiệu
│   ├── 02_literature_review.tex ← Chương 2: Tổng quan nghiên cứu
│   ├── 03_data_pipeline.tex  ← Chương 3: Data Pipeline
│   ├── 04_model_selection.tex ← Chương 4: Tích hợp model & hướng tối ưu hóa
│   ├── 05_backend.tex        ← Chương 5: Backend & tích hợp
│   ├── 06_frontend.tex       ← Chương 6: Frontend
│   ├── 07_infrastructure.tex ← Chương 7: Hạ tầng triển khai
│   ├── 08_experiments.tex    ← Chương 8: Kiểm chứng ứng dụng & giới hạn thực nghiệm
│   ├── 09_ethics.tex         ← Chương 9: Bảo mật & đạo đức AI
│   ├── 10_conclusion.tex     ← Chương 10: Kết luận
│   └── appendix.tex          ← Phụ lục A–E
└── figures/                  ← Thư mục chứa hình ảnh (PNG/PDF)
    └── .gitkeep
```

---

## Cách import vào Overleaf

1. Nén toàn bộ thư mục thành file ZIP
2. Vào [overleaf.com](https://overleaf.com) → New Project → Upload Project
3. Upload file ZIP
4. Overleaf sẽ tự nhận diện `main.tex` làm file chính
5. Chọn **Compiler**: `pdfLaTeX`
6. Nhấn **Compile** (Ctrl+Enter)

---

## Cài đặt Overleaf cho tiếng Việt

Trong Overleaf Menu (biểu tượng hamburger góc trên trái):
- **Compiler**: pdfLaTeX
- **TeX Live version**: 2023 (hoặc mới nhất)

Packages tiếng Việt đã được include trong `main.tex`:
```latex
\usepackage[utf8]{inputenc}
\usepackage[T5]{fontenc}
\usepackage[vietnamese]{babel}
```

---

## Các chỗ cần hoàn thiện trước khi nộp

Tìm kiếm `\needvalue{` trong tất cả file để điền thông tin sinh viên và thời gian.

Chỉ thêm số liệu model, ASR, latency hoặc tải khi có log/artefact đo tương ứng; không điền số liệu giả định.

---

## Thêm hình ảnh

1. Upload ảnh vào thư mục `figures/` trong Overleaf
2. Trong file `.tex`, sử dụng:

```latex
\begin{figure}[H]
  \centering
  \includegraphics[width=0.9\textwidth]{figures/ten-hinh.png}
  \caption{Chú thích hình}
  \label{fig:ten-nhan}
\end{figure}
```

3. Thay thế lệnh `\figplaceholder{...}{...}` bằng `figure` environment thực sự.

---

## Biên dịch local (nếu cần)

```bash
# Yêu cầu: TeX Live 2023+ với gói tiếng Việt
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

---

## Lưu ý

- Tất cả file được encode UTF-8
- Font Times New Roman được sử dụng qua package `times`
- Tài liệu tham khảo theo chuẩn IEEE (`IEEEtran`)
- Màu sắc theme: `primaryblue` (#1F4E79), `accentblue` (#2980B9)
