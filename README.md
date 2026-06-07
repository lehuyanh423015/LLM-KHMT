# Continual Learning Shopping Assistant Chatbot

Demo chatbot tư vấn mua sắm cho đồ án **Memory-based Continual Learning for Conversational AI**.

Dự án tập trung vào một thử nghiệm nhỏ nhưng hoàn chỉnh: chatbot có thể ghi nhớ nhu cầu của khách hàng trong cuộc hội thoại, dùng bộ nhớ đó cùng catalog sản phẩm để đưa ra gợi ý mua điện thoại/laptop phù hợp hơn theo thời gian.

## Mục tiêu

- Xây dựng chatbot tư vấn mua sắm có khả năng ghi nhớ thông tin người dùng.
- Minh họa continual learning ở mức memory-based: ngân sách, danh mục, nhu cầu, ưu tiên, hãng thích/không thích, hệ điều hành muốn tránh.
- Kết hợp LLM local qua Ollama với logic catalog/retrieval để trả lời ổn định.
- Tách backend thành kiến trúc dễ hiểu, dễ demo và dễ chia việc giữa hai thành viên.

## Công nghệ

- Frontend: Next.js, React, TypeScript, Tailwind CSS
- Backend: FastAPI, SQLAlchemy, SQLite
- LLM local: Ollama
- Model mặc định: `qwen3:4b`
- Catalog demo: `apps/backend/data/mini_product_catalog.json`
- Memory: SQLite customer profile + recent conversation context

## Kiến trúc chính

```text
Frontend
  -> FastAPI route
  -> Chat Orchestrator
  -> Recent conversation context
  -> Customer memory context
  -> Product catalog/retrieval context
  -> Grounded answer / optional LLM rewrite
  -> Save conversation
  -> Update customer memory
```

Các file backend quan trọng:

- `apps/backend/services/chat_orchestrator.py`: điều phối luồng chat chính.
- `apps/backend/routes/chat.py`: route mỏng, chỉ nhận request và gọi orchestrator.
- `apps/backend/services/memory_service.py`: trích xuất và cập nhật customer memory.
- `apps/backend/services/retrieval_service.py`: format customer memory context.
- `apps/backend/services/product_retrieval_service.py`: tìm sản phẩm từ catalog và tạo product context.
- `apps/backend/services/answer_planning_service.py`: dựng câu trả lời grounded theo từng kiểu câu hỏi.
- `apps/backend/services/llm/ollama_provider.py`: gọi Ollama và rewrite câu trả lời khi cần.
- `apps/backend/core/config.py`: cấu hình model, database và experiment flags.

## Phạm vi demo hiện tại

Chatbot hoạt động tốt nhất với:

- Điện thoại trong nhiều tầm giá.
- Laptop phổ thông, văn phòng, gaming, creator, hiệu năng cao.
- Câu hỏi gợi ý sản phẩm theo ngân sách/nhu cầu/hãng.
- Câu hỏi cấu hình chi tiết của sản phẩm trong catalog.
- Câu hỏi so sánh sản phẩm có trong catalog.
- Follow-up theo memory, ví dụ đổi ngân sách, đổi hãng, không thích Apple/iOS, muốn hãng khác.
- Câu xã giao cơ bản như cảm ơn, chốt mua, hỏi chuyện thông thường.

Đây không phải hệ thống bán hàng hoàn chỉnh. Catalog là dữ liệu demo, giá và cấu hình cần kiểm tra lại trước khi mua thật.

## Continual Learning trong dự án

Dự án không fine-tune LLM. Continual learning được minh họa bằng hướng **memory-based continual learning**:

- Người dùng nói ngân sách, ví dụ `khoảng 50 triệu`.
- Chatbot lưu vào customer profile.
- Người dùng nói tiếp `cho tôi vài mẫu Lenovo`.
- Chatbot dùng lại category, budget và priority đã nhớ để trả lời.
- Nếu người dùng đổi nhu cầu, ví dụ `không chơi game nữa, ưu tiên pin và camera`, memory sẽ cập nhật lại ưu tiên.

Các trường memory chính:

- Budget
- Category
- Color
- Priorities
- Dislikes
- Preferred/disliked brands
- Preferred/disliked OS

## Cài đặt

### 1. Yêu cầu

- Python 3.10+
- Node.js 20+
- pnpm
- Ollama

### 2. Clone project

```bash
git clone <repo-url>
cd LLM-KHMT
```

### 3. Cài Ollama model

```bash
ollama pull qwen3:4b
ollama pull qwen2.5:0.5b
```

`qwen3:4b` dùng cho trả lời chính. `qwen2.5:0.5b` dùng cho các bước rewrite/casual nhẹ nếu được bật trong config.

### 4. Tạo file môi trường

```bash
cp .env.example .env
```

Cấu hình demo ổn định khuyến nghị:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b

ENABLE_MEMORY=true
ENABLE_RECENT_CONTEXT=true
ENABLE_PRODUCT_CONTEXT=true
ENABLE_GROUNDED_PRODUCT_ANSWER=true
ENABLE_WEB_SEARCH=false
ENABLE_EXTERNAL_PRODUCT_SEARCH=false
```

Ghi chú:

- `ENABLE_GROUNDED_PRODUCT_ANSWER=true` là chế độ demo ổn định nhất, trả lời nhanh từ catalog/template.
- LLM vẫn có thể dùng để rewrite/casual chat, nhưng hệ thống không phụ thuộc vào LLM để chọn sản phẩm.
- External web search đã để tắt vì không ổn định cho demo.

## Chạy backend

```bash
cd apps/backend

python -m venv venv
venv\Scripts\activate

python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt

uvicorn main:app --reload --port 8000
```

Kiểm tra backend:

```bash
curl http://localhost:8000/health
```

## Chạy frontend

Mở terminal khác:

```bash
cd apps/frontend
pnpm install
pnpm dev
```

Truy cập:

```text
http://localhost:3000
```

## API chính

### POST `/chat`

Request:

```json
{
  "message": "tôi muốn mua laptop gaming khoảng 30 triệu",
  "session_id": "demo-session"
}
```

Response:

```json
{
  "answer": "...",
  "session_id": "demo-session",
  "debug": {
    "active_model": "qwen3:4b",
    "answer_strategy": "grounded_template",
    "memory_enabled": true,
    "recent_context_enabled": true,
    "product_context_enabled": true,
    "product_context_loaded": true
  }
}
```

### GET `/health`

Kiểm tra cấu hình backend, model active, trạng thái Ollama và các experiment flags.

```bash
curl http://localhost:8000/health
```

### GET `/customer-profile/{session_id}`

Xem customer memory hiện tại của một session.

```bash
curl http://localhost:8000/customer-profile/demo-session
```

## Kịch bản demo gợi ý

### 1. Memory theo ngân sách và nhu cầu

```text
tôi muốn mua laptop gaming khoảng 30 triệu
```

Sau đó hỏi tiếp:

```text
nếu tôi tăng lên khoảng 50 triệu thì có mẫu nào tốt hơn không
```

Kỳ vọng: chatbot cập nhật ngân sách và đề xuất laptop ở phân khúc cao hơn.

### 2. Đổi hãng theo follow-up

```text
tôi muốn tham khảo vài mẫu Apple
```

Sau đó:

```text
vậy cho tôi vài mẫu laptop Lenovo
```

Kỳ vọng: chatbot vẫn giữ category/budget đã nhớ, nhưng đổi brand theo câu mới.

### 3. Ghi nhớ dislike

```text
tôi không thích dùng iOS, ưu tiên Android
```

Kỳ vọng: memory ghi nhận dislike iOS/Apple và ưu tiên Android.

### 4. Cấu hình chi tiết

```text
cho tôi cấu hình chi tiết của iQOO 13
```

Kỳ vọng: chatbot trả thông số cụ thể từ catalog như chipset, RAM, bộ nhớ, màn hình, pin, sạc, camera.

### 5. So sánh sản phẩm

```text
so sánh Xiaomi 14 và Realme GT 7 Pro
```

Kỳ vọng: chatbot nêu cả hai sản phẩm, thông số chính, điểm hơn/kém và gợi ý chọn theo nhu cầu.

## Chạy test

Từ thư mục gốc:

```bash
python -m unittest apps.backend.tests.test_product_retrieval_service apps.backend.tests.test_query_understanding_service apps.backend.tests.test_memory_service apps.backend.tests.test_chat_orchestrator apps.backend.tests.test_clarification_flow
```

Lần kiểm tra cuối của dự án:

```text
76 tests OK
```

## Giới hạn hiện tại

- Catalog là dữ liệu demo, không phải dữ liệu bán hàng thời gian thực.
- Không tự crawl web trong flow chính.
- Không fine-tune hoặc continual train LLM.
- Continual learning được minh họa qua memory update, không phải cập nhật trọng số model.
- Các câu quá mơ hồ vẫn có thể cần hỏi lại hoặc phụ thuộc vào context gần nhất.
- Giá/cấu hình trong catalog cần kiểm tra lại nếu dùng cho quyết định mua thật.

## Đóng góp học thuật

Dự án phù hợp với yêu cầu demo cuối kỳ ở mức lightweight experiment:

- Hiểu bài toán: chatbot tư vấn mua sắm cần ghi nhớ nhu cầu theo thời gian.
- Literature direction: continual learning cho conversational AI, memory-augmented agents, retrieval-grounded generation.
- Phương pháp: memory-based continual learning + grounded product retrieval + local LLM synthesis.
- Demo nhỏ: FastAPI/Next.js chatbot có memory, catalog, follow-up context và giao diện debug memory.

## Trạng thái cuối

Dự án đã được chốt ở trạng thái ưu tiên ổn định:

- Backend chạy được.
- Frontend chạy được.
- Chat endpoint hoạt động.
- Memory update hoạt động.
- Product catalog retrieval hoạt động.
- Grounded answer hoạt động.
- Câu xã giao cơ bản không còn bị đẩy nhầm sang product flow.
- Các lỗi chính trong quá trình demo đã được khóa bằng test.

Đây là phiên bản kết thúc để nộp/demo cho đồ án.
