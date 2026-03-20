<p align="center">
  <img src="Image/logoViEng.jpg" alt="ViEng Logo" width="200" />
</p>

<h1 align="center">ViEng - Trợ lý luyện thi tiếng Anh AI</h1>

<p align="center">
  <strong>Cho sinh viên Việt Nam</strong>
</p>

## Giới thiệu

ViEng là ứng dụng web hỗ trợ sinh viên Việt Nam luyện thi TOEIC/IELTS một cách cá nhân hóa, sử dụng AI để tạo bài tập, phân tích lỗi sai, dịch thuật thông minh, và cung cấp feedback tức thì theo phong cách "thầy cô Việt".

### Sơ lược (Technical Highlights)

- **RAG Pipeline**: ChromaDB + HuggingFace embeddings (paraphrase-multilingual) — tra cứu ngữ pháp/từ vựng khi giải thích đáp án
- **LLM Integration**: Groq (Llama-3.3-70B) / OpenAI (GPT-4o-mini) — tạo đề thi, giải thích, dịch thuật
- **Fine-tuning**: Qwen2.5-7B với QLoRA + Unsloth trên Colab T4; dataset 500+ mẫu sinh tự động từ Groq API
- **Token handling**: Batching để sinh đề 100 câu; giải thích on-demand khi user xem từng câu
- **Stack**: FastAPI, React, LangChain, ChromaDB, sentence-transformers

### Tính năng chính

- **Tạo đề thi TOEIC đúng format**: Part 5 (Incomplete Sentences), Part 6 (Text Completion), Part 7 (Single & Multiple Passages)
- **Phân tích và giải thích lỗi**: Feedback chi tiết, thân thiện theo phong cách thầy cô Việt Nam
- **Chatbot RAG + LLM**: Hỏi đáp ngữ pháp, từ vựng TOEIC/IELTS — AI trả lời dựa trên knowledge base
- **Dịch thuật AI + RAG**: Dịch Anh-Việt / Việt-Anh thông minh, kèm từ vựng quan trọng và ghi chú ngữ pháp
- **RAG integration**: Tra cứu knowledge base (grammar rules, từ vựng, collocations) để đảm bảo giải thích chính xác
- **Fine-tune LLM (RAG-augmented)**: Fine-tune Qwen2.5-7B bằng QLoRA + Unsloth, training data có kèm RAG context
- **RAG-augmented Generation**: Tạo đề thi & giải thích đều sử dụng knowledge base qua RAG pipeline

## Tech Stack

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.11 + FastAPI |
| Frontend | React 19 + Vite 6 + TailwindCSS 4 |
| LLM | Groq (Llama-3.3-70B) / OpenAI (GPT-4o-mini) / Fine-tuned Qwen2.5-7B |
| RAG | LangChain + ChromaDB |
| Embeddings | sentence-transformers (multilingual) |
| Fine-tune | Unsloth + QLoRA (Google Colab T4) |
| Testing | pytest |

## Cấu trúc dự án

```
ViEng/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── api/
│   │   └── routes.py            # API endpoints
│   ├── core/
│   │   └── config.py            # Settings & environment
│   ├── models/
│   │   └── schemas.py           # Pydantic data models
│   ├── services/
│   │   ├── llm_service.py       # LLM integration (Groq/OpenAI/HF)
│   │   └── rag_service.py       # RAG pipeline (ChromaDB)
│   └── utils/
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.jsx         # Trang chủ
│   │   │   ├── Exam.jsx         # Làm bài thi TOEIC Part 5/6/7
│   │   │   ├── Result.jsx       # Kết quả + feedback
│   │   │   ├── Chat.jsx         # Chatbot RAG+LLM
│   │   │   └── Translate.jsx    # Dịch thuật AI
│   │   ├── components/
│   │   │   └── Layout.jsx       # Layout chung (header, nav, footer)
│   │   ├── api.js               # API client (axios)
│   │   ├── App.jsx              # Router chính
│   │   └── main.jsx             # Entry point React
│   ├── package.json
│   └── vite.config.js
├── scripts/
│   ├── generate_finetune_dataset.py  # Sinh dataset fine-tune từ Groq API
│   └── download_datasets.py          # Tải dataset từ HuggingFace
├── data/
│   ├── knowledge_base/          # Tài liệu grammar, từ vựng (.txt)
│   └── finetune_dataset.jsonl   # Dataset fine-tune LLM
├── tests/
│   └── test_api.py
├── FineTune_ViEng.ipynb         # Notebook Colab fine-tune LLM
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

### 2. Backend

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Frontend

```bash
cd frontend
npm install --legacy-peer-deps
cd ..
```

### 4. Cấu hình environment

```bash
cp .env.example .env
```

Mở file `.env` và thêm API key:
- **Groq** (miễn phí): Đăng ký tại [console.groq.com](https://console.groq.com) để lấy `GROQ_API_KEY`
- **OpenAI** (trả phí): Thêm `OPENAI_API_KEY` nếu muốn dùng GPT

### 5. Chạy ứng dụng

```bash
# Terminal 1 - Backend
uvicorn app.main:app --reload

# Terminal 2 - Frontend
cd frontend
npm run dev
```

Truy cập:
- Frontend: http://localhost:5173
- API Swagger: http://localhost:8000/docs

## API Endpoints

| Method | Endpoint | Mô tả |
|---|---|---|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/test/generate` | Tạo đề thi TOEIC/IELTS (Part 5/6/7) |
| POST | `/api/v1/test/submit` | Nộp bài & nhận feedback + giải thích |
| POST | `/api/v1/chat` | Chatbot RAG+LLM — hỏi đáp ngữ pháp/từ vựng |
| POST | `/api/v1/translate` | Dịch thuật AI (EN↔VI) + từ vựng + ngữ pháp |
| GET | `/api/v1/rag/list` | Liệt kê chunks trong vectorstore |
| POST | `/api/v1/rag/index` | Index knowledge base vào vectorstore |
| POST | `/api/v1/rag/search` | Tìm kiếm trong knowledge base |

## TOEIC Reading Format

Đề thi được sinh đúng format chuẩn TOEIC:

| Part | Dạng bài | Số câu chuẩn |
|---|---|---|
| Part 5 | Incomplete Sentences (hoàn thành câu) | 30 câu |
| Part 6 | Text Completion (hoàn thành đoạn văn) | 16 câu (4 đoạn × 4 câu) |
| Part 7 Single | Single Passage (đọc hiểu 1 đoạn) | 29 câu |
| Part 7 Multiple | Multiple Passages (đọc hiểu 2-3 đoạn) | 25 câu (5 bộ × 5 câu) |

## Fine-tune LLM (RAG-augmented)

Dự án hỗ trợ fine-tune model Qwen2.5-7B trên Google Colab miễn phí, với **RAG-augmented training data**:

1. **Index knowledge base**: Đảm bảo `data/knowledge_base/` có các file .txt (grammar, vocabulary, strategies)
2. **Sinh dataset RAG-augmented**: `python scripts/generate_finetune_dataset.py`
   - Script tự khởi tạo RAG retriever từ knowledge base
   - Mỗi training example có kèm **RAG context** (tài liệu ngữ pháp/từ vựng liên quan)
   - Model học cách **sử dụng retrieved context** khi generate
3. **Upload** file `data/finetune_dataset.jsonl` lên Colab
4. **Mở** `FineTune_ViEng.ipynb` trên Colab (chọn GPU T4)
5. **Chạy** từng cell: cài thư viện → load model → train → lưu adapter

Sau fine-tune, bật trong `.env`:
```env
USE_FINETUNED_MODEL=true
HF_MODEL_NAME=LeNhan18/ViEng-Qwen2.5-7B-lora
```

## Chạy tests

```bash
pytest tests/ -v
```

## Roadmap

- [x] Cấu trúc dự án & API cơ bản
- [x] Tích hợp LLM (Groq/OpenAI) tạo đề + giải thích
- [x] Knowledge base (20+ file grammar, vocabulary, strategies)
- [x] RAG pipeline (ChromaDB + embeddings)
- [x] Frontend React (Trang chủ, Làm bài, Kết quả, Dịch thuật)
- [x] TOEIC Reading đúng format Part 5/6/7
- [x] Chức năng dịch thuật AI + RAG
- [x] Script sinh dataset fine-tune
- [x] Notebook Colab fine-tune (QLoRA + Unsloth)
- [x] Tích hợp fine-tuned model vào backend
- [ ] Thêm dữ liệu đề thi TOEIC thật vào knowledge base
- [ ] Lưu trữ session & tiến độ học tập
- [ ] IELTS Reading/Writing format
- [ ] Voice mode (Whisper)

## Đối tượng sử dụng

Sinh viên đại học, người đi làm cần chứng chỉ TOEIC/IELTS.

## License

MIT
