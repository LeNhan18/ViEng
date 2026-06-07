# Tài liệu hướng dẫn tích hợp Chat Memory (Redis & MySQL)

Tài liệu này giải thích chi tiết các thành phần code được thêm mới và sửa đổi để xây dựng tính năng bộ nhớ chat (Chat Memory) cho từng người dùng, hỗ trợ đồng thời cả **Redis** (cho bộ nhớ đệm tốc độ cao) và **MySQL Database** (lưu trữ bền vững lâu dài).

---

## 1. Thiết kế Hệ thống Bộ nhớ Chat (Architecture)

Khi người dùng gửi tin nhắn trên giao diện Chatbot:
1. **Kiểm tra Xác thực (Authentication check)**: Backend giải mã JWT token để tìm `user_id` từ yêu cầu (ở dạng tùy chọn, nếu không đăng nhập hệ thống vẫn chạy ở chế độ stateless bình thường).
2. **Đọc lịch sử (Get history)**:
   - Hệ thống tìm lịch sử chat trong **Redis** bằng key `vieng:chat_history:{user_id}`.
   - Nếu Redis rỗng hoặc bị lỗi kết nối, hệ thống sẽ truy vấn bảng `chat_messages` trong **MySQL**.
   - Nếu tìm thấy dữ liệu từ MySQL, hệ thống tự động đồng bộ lại cache sang **Redis** để tăng tốc cho lần truy cập sau.
3. **Gọi mô hình LLM**: Lịch sử hội thoại (tối đa 10 tin nhắn gần nhất) sẽ được gửi kèm câu hỏi mới của người dùng tới mô hình ngôn ngữ (Groq hoặc OpenAI).
4. **Lưu tin nhắn (Save messages)**:
   - Câu hỏi của người dùng và câu trả lời của AI sẽ được lưu trữ đồng thời vào **Redis** và **MySQL**.
   - Phía Redis áp dụng hàm `ltrim` để giữ tối đa **100 tin nhắn gần nhất** nhằm tối ưu hóa bộ nhớ RAM của Redis server.

---

## 2. Chi tiết các File thay đổi (Modified Files)

### 2.1 Backend (Python / FastAPI / SQLAlchemy)

* **[requirements.txt](requirements.txt)**:
  - Thêm thư viện `redis>=5.0.0` để kết nối và thao tác với máy chủ Redis/Redict một cách bất đồng bộ (`redis.asyncio`).
* **[app/core/config.py](app/core/config.py)**:
  - Thêm các thuộc tính cấu hình trong lớp `Settings` để cấu hình Redis qua file `.env`: `use_redis`, `redis_host`, `redis_port`, `redis_password`, `redis_db`.
* **[.env.example](.env.example)** & **[.env](.env)**:
  - Bổ sung cấu hình Redis mặc định:
    ```env
    USE_REDIS=false
    REDIS_HOST=127.0.0.1
    REDIS_PORT=6379
    REDIS_PASSWORD=
    REDIS_DB=0
    ```
* **[app/models/orm.py](app/models/orm.py)**:
  - Định nghĩa model `ChatMessage` tương ứng với bảng cơ sở dữ liệu `chat_messages` lưu trữ: `user_id`, `role`, `content`, `sources` (dưới dạng JSON string) và thời gian tạo `created_at`.
* **[app/services/chat_memory_service.py](app/services/chat_memory_service.py) [NEW]**:
  - Chứa lớp `ChatMemoryService` quản lý toàn bộ logic đọc/ghi/xóa dữ liệu trên Redis và DB.
  - Sử dụng kết nối an toàn với cơ chế bắt lỗi `try-except` cho Redis và MySQL, bảo đảm nếu dịch vụ lưu trữ gặp sự cố, luồng chat chính của người dùng vẫn hoạt động bình thường (stateless fallback).
* **[app/api/routes.py](app/api/routes.py)**:
  - Viết dependency `_get_current_user_optional` cho phép đọc JWT Token tùy chọn của người dùng mà không chặn bằng lỗi 401 khi không đăng nhập.
  - Tích hợp lưu trữ vào endpoint `/chat` và `/chat/ocr`.
  - Thêm hai endpoint mới: `GET /api/v1/chat/history` (tải lịch sử chat của user) và `DELETE /api/v1/chat/history` (xóa lịch sử chat của user).

### 2.2 Frontend (React / Axios)

* **[frontend/src/api.js](frontend/src/api.js)**:
  - Xuất thêm 2 hàm API wrapper mới: `getChatHistory()` và `clearChatHistory()`.
* **[frontend/src/pages/Chat.jsx](frontend/src/pages/Chat.jsx)**:
  - Thêm hook `useEffect` gọi `getChatHistory()` khi màn hình chat được mở ra (chỉ khi có token đăng nhập).
  - Tích hợp nút **"Xóa lịch sử"** (Clear history) hiển thị trên thanh tiêu đề toolbar khi người dùng đã đăng nhập và có tin nhắn.
  - Cập nhật hàm gọi `/chat` để tự động làm việc cùng bộ nhớ đầu cuối ở backend.

---

## 3. Cách chạy thử và cấu hình

1. **Khởi chạy Redis Server** (nếu có):
   ```bash
   # Nếu dùng Docker:
   docker run -d --name redis-vieng -p 6379:6379 redis:alpine
   ```
2. **Kích hoạt trong file `.env`**:
   ```env
   USE_DATABASE=true  # Kích hoạt MySQL
   USE_REDIS=true     # Kích hoạt Redis
   REDIS_HOST=127.0.0.1
   REDIS_PORT=6379
   ```
3. **Cài đặt thư viện và khởi động**:
   ```bash
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
4. **Mở trình duyệt** đăng nhập vào tài khoản trên giao diện Web UI, truy cập menu **Chatbot** để trải nghiệm lịch sử hội thoại được tự động tải lại mỗi khi tải lại trang!
