# Hướng Dẫn Thiết Lập Dự Án Cho Thành Viên Nhóm (Team Setup Guide)

Chào mừng các bạn đến với dự án **Shopping Assistant AI (Continual Learning)**. Đây là tài liệu hướng dẫn chi tiết để các bạn có thể cài đặt và chạy dự án này trên máy cá nhân một cách nhanh chóng nhất.

---

## 🛠 1. Công cụ & Phần mềm bắt buộc (Requirements)

Trước khi bắt đầu, hãy đảm bảo máy tính của bạn đã cài đặt các công cụ sau:

1.  **Node.js (>= 20.x)**: Tải tại [nodejs.org](https://nodejs.org/).
2.  **Python (>= 3.10.x)**: Tải tại [python.org](https://www.python.org/). *Lưu ý: Nhớ tick "Add Python to PATH" khi cài đặt trên Windows.*
3.  **pnpm**: Trình quản lý gói cho Frontend. Cài đặt bằng lệnh:
    ```bash
    npm install -g pnpm
    ```
4.  **Ollama**: Công cụ chạy LLM local. Tải tại [ollama.com](https://ollama.com/).

---

## 📥 2. Tải và Cài đặt Dự án

### Bước 1: Clone dự án
Sử dụng Git để tải mã nguồn:
```bash
git clone <[url-repo-cua-nhom](https://github.com/lehuyanh423015/LLM-KHMT.git)>
cd LLM-KHMT
```

### Bước 2: Thiết lập Backend (Python - FastAPI)
```bash
cd apps/backend

# Tạo môi trường ảo
python -m venv venv

# Kích hoạt môi trường ảo
# Windows:
venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# Cài đặt thư viện
pip install -r requirements.txt
```

### Bước 3: Thiết lập Frontend (Next.js)
Mở một Terminal mới (vẫn ở thư mục gốc `LLM-KHMT`):
```bash
cd apps/frontend
pnpm install
```

### Bước 4: Thiết lập Biến môi trường
Tại thư mục gốc của dự án, sao chép file `.env.example` thành `.env`:
```bash
cp .env.example .env
```

### Bước 5: Cài đặt Model cho Ollama
Mở Ollama và chạy 2 lệnh sau để tải model về máy:
```bash
ollama pull qwen2.5:0.5b
ollama pull qwen3:4b
```

---

## 🚀 3. Cách khởi chạy dự án

Bạn cần chạy **cả Backend và Frontend** cùng một lúc:

1.  **Chạy Backend**: (Tại `apps/backend`, nhớ đã activate `venv`)
    ```bash
    uvicorn main:app --reload --port 8000
    ```
2.  **Chạy Frontend**: (Tại `apps/frontend`)
    ```bash
    pnpm dev
    ```
3.  **Truy cập**: Mở trình duyệt tại [http://localhost:3000](http://localhost:3000).

---

## 💻 4. Công cụ lập trình (IDE) & Extensions

Dự án khuyến khích sử dụng các công cụ sau để code hiệu quả:

### A. Đối với VS Code (Khuyên dùng)
Hãy cài đặt các Extensions (Tiện ích mở rộng) sau:
- **Python**: Hỗ trợ debug, linting cho Backend.
- **ESLint** & **Prettier**: Để tự động format code Frontend đẹp và đồng nhất.
- **Tailwind CSS IntelliSense**: Hỗ trợ gợi ý code CSS nhanh hơn.
- **SQLite Viewer**: Để xem dữ liệu trong file `app.db` trực tiếp trên VS Code.

### B. Đối với IntelliJ IDEA / WebStorm / PyCharm
- Tải plugin **Python** (nếu dùng IntelliJ bản Ultimate).
- Đảm bảo đã chọn đúng thông dịch viên (Interpreter) là file python trong thư mục `venv`.
- Bật hỗ trợ **Node.js và NPM** trong Settings.

---

## 📝 5. Lưu ý quan trọng cho nhóm

-   **File Cơ sở dữ liệu**: Khi bạn chạy dự án lần đầu, file `app.db` (SQLite) sẽ tự động được tạo ở thư mục `apps/backend`. Bạn không cần commit file này lên Git.
-   **Quy trình làm việc**: Trước khi code, hãy chạy `git pull` để cập nhật mã nguồn mới nhất từ các thành viên khác.
-   **Chế độ Model**:
    -   Nếu máy yếu: Dùng chế độ **FAST** (mặc định qwen2.5:0.5b).
    -   Nếu máy mạnh/Cần độ chính xác cao: Chuyển sang chế độ **QUALITY** (Star icon trên UI).

Nếu gặp lỗi trong quá trình cài đặt, hãy chụp màn hình Terminal và gửi vào nhóm chat của chúng mình nhé! Chúc cả nhóm làm việc hiệu quả! 🚀
