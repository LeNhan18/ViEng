# ViEng - Trợ lý luyện thi tiếng Anh AI cho sinh viên Việt Nam

## Giới thiệu

ViEng là ứng dụng web hỗ trợ sinh viên Việt Nam luyện thi TOEIC/IELTS một cách cá nhân hóa, sử dụng AI để tạo bài tập, phân tích lỗi sai, và cung cấp feedback tức thì theo phong cách "thầy cô Việt".

### Tính năng chính

- **Tạo bài test cá nhân hóa**: Chọn kỹ năng (Listening, Reading, Speaking, Writing) và trình độ (Beginner/Intermediate/Advanced)
- **Phân tích và giải thích lỗi**: Feedback chi tiết, thân thiện theo phong cách thầy cô Việt Nam
- **RAG integration**: Trích dẫn nguồn uy tín (grammar rules, từ vựng) để đảm bảo chính xác
- **Tiến độ tracking**: Dashboard theo dõi điểm số và điểm yếu

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.11 + FastAPI |
| LLM | Groq (Llama-3.3-70B) / OpenAI (GPT-4o-mini) |
| RAG | LangChain + ChromaDB |
| Embeddings | sentence-transformers (multilingual) |
| Frontend | Streamlit (prototype) |
| Testing | pytest |

## Cấu trúc dự án

```
ViEng/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── api/
│   │   └── routes.py        # API endpoints
│   ├── core/
│   │   └── config.py        # Settings & environment
│   ├── models/
│   │   └── schemas.py       # Pydantic data models
│   ├── services/
│   │   ├── llm_service.py   # LLM integration (Groq/OpenAI)
│   │   └── rag_service.py   # RAG pipeline (ChromaDB)
│   └── utils/
├── data/
│   └── knowledge_base/      # Tài liệu grammar, từ vựng (.txt)
├── tests/
│   └── test_api.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Cài đặt

### 1. Clone repo

```bash
git clone https://github.com/LeNhan18/ViEng.git
cd ViEng
```

### 2. Tạo virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Cài dependencies

```bash
pip install -r requirements.txt
```

### 4. Cấu hình environment

```bash
cp .env.example .env
```

Mở file `.env` và thêm API key:
- **Groq** (miễn phí): Đăng ký tại [console.groq.com](https://console.groq.com) để lấy `GROQ_API_KEY`
- **OpenAI** (trả phí): Thêm `OPENAI_API_KEY` nếu muốn dùng GPT

### 5. Chạy server

```bash
uvicorn app.main:app --reload
```

Truy cập:
- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs

## API Endpoints

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/` | Thông tin app |
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/test/generate` | Tạo bài test |
| POST | `/api/v1/test/submit` | Nộp bài & nhận feedback |
| POST | `/api/v1/rag/index` | Index knowledge base |
| POST | `/api/v1/rag/search` | Tìm kiếm trong knowledge base |

## Chạy tests

```bash
pytest tests/ -v
```

## Roadmap

- [x] Cấu trúc dự án & API cơ bản
- [ ] Tích hợp LLM hoàn chỉnh (generate + explain)
- [ ] Xây dựng knowledge base (grammar, vocabulary)
- [ ] RAG pipeline end-to-end
- [ ] Frontend Streamlit
- [ ] Lưu trữ session & tiến độ học tập
- [ ] Voice mode (Whisper)
- [ ] Fine-tune LLM với LoRA

## Đối tượng sử dụng

Sinh viên đại học, người đi làm cần chứng chỉ TOEIC/IELTS.

## License

MIT
