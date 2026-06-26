<p align="center">
  <img src="Image/logoViEng.jpg" alt="ViEng Logo" width="180" />
</p>

<h1 align="center">ViEng</h1>

<p align="center">
  <strong>AI-powered TOEIC/IELTS exam preparation platform for Vietnamese learners</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-61DAFB?style=flat-square&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/Flutter-02569B?style=flat-square&logo=flutter&logoColor=white" alt="Flutter" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Kubernetes-326CE5?style=flat-square&logo=kubernetes&logoColor=white" alt="Kubernetes" />
  <img src="https://img.shields.io/badge/CUDA-11.8+-76B900?style=flat-square&logo=nvidia&logoColor=white" alt="CUDA" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License" />
</p>

<p align="center">
  <strong>Demo</strong><br />
  <video src="https://raw.githubusercontent.com/LeNhan18/ViEng/main/Image/ViEng.mp4" controls width="640"></video>
  <br />
  <em>If the video does not play, <a href="https://github.com/LeNhan18/ViEng/blob/main/Image/ViEng.mp4?raw=true">click here</a>.</em>
</p>

<p align="center">
  <strong>Demo (ViEng2)</strong><br />
  <a href="https://www.youtube.com/watch?v=U4Ak4mDY-zk">▶ Watch ViEng2 demo (project video)</a>
</p>

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Installation & Quickstart](#installation--quickstart)
- [Environment Configuration](#environment-configuration)
- [LLM & VLM Providers](#llm--vlm-providers)
- [GPU Acceleration & Cache Redirect](#gpu-acceleration--cache-redirect)
- [API Reference](#api-reference)
- [Document Parsing & RAG Ingestion](#document-parsing--rag-ingestion)
- [Fine-tuning Workflow](#fine-tuning-workflow)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

**ViEng** is an advanced AI-assisted English exam preparation ecosystem tailored specifically for Vietnamese learners. It features a responsive **web application** (React) and an optional **mobile application** (Flutter/Android), powered by a **RAG (Retrieval-Augmented Generation)** knowledge retrieval engine and dynamic LLM backends.

The platform is designed to:
- Generate highly realistic TOEIC/IELTS-style practice tests and questions.
- Provide detailed answer explanations in a friendly, conversational "Vietnamese teacher" style.
- Support chat-based Q&A with context memory, grounded in a customizable local knowledge base.
- Extract complex structures (tables, formulas, texts) from scanned exam sheets or documents using high-fidelity OCR.
- Perform English-to-Vietnamese translation with automatic key vocabulary extraction, grammar notes, and TTS voice output.

---

## Key Features

- **Realistic TOEIC Practice Modules**:
  - **Part 5**: Incomplete Sentences (vocabulary & grammar focus).
  - **Part 6**: Text Completion (passage-level blanks).
  - **Part 7**: Single & Multiple Passages (reading comprehension).
  - *(Lưu ý: Hiện tại hệ thống chỉ hỗ trợ phần Reading từ Part 5 đến Part 7. Các phần Listening từ Part 1 đến Part 4 đang nằm trong lộ trình phát triển).*
- **Intelligent Explanations**: Deep contextual analysis tailored by question part (sentence-level vs. passage-level logical reasoning).
- **Context-Aware RAG Chatbot**: Persistent session memory via **Redis/Redict** & **MySQL** database fallback. Grounded responses cite specific sourced documents.
- **GPU-Accelerated Document Parsing (PP-StructureV3 & PP-OCRv6)**:
  - Advanced layout analysis to segment images and PDFs.
  - State-of-the-art text, table (HTML format), and LaTeX mathematical formula recognition.
  - Native integration with the RAG pipeline to ingest scanned/visual materials.
- **Interactive EN↔VI Translation**:
  - Extracts key vocabulary list with definitions.
  - Lists important grammatical patterns present in the sentence.
  - English speech synthesis using **Edge TTS**.

---

## System Architecture

```mermaid
graph TD
    Client[Client React / Flutter] -->|API Requests| Backend[FastAPI Backend]
    Backend -->|Check Auth & History| DB[(MySQL Database)]
    Backend -->|Fast Cache History| Cache[(Redis Session Cache)]
    Backend -->|Retrieve Context| RAG[RAG Retrieval Engine]
    RAG -->|Similarity Search| Vector[(ChromaDB Vector Store)]
    Backend -->|GPU Layout & OCR| OCR[PP-OCRv6 / PP-StructureV3]
    Backend -->|Generate Answers| LLM[Groq / OpenAI / HF Local Qwen]
```

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.11+, FastAPI |
| **Web Frontend** | React 18, Vite, TailwindCSS |
| **Mobile Frontend** | Flutter (Android SDK) |
| **LLM Inference** | Groq API / OpenAI API / Hugging Face Inference API / Local Transformers |
| **OCR & Layout** | PP-OCRv6, PP-StructureV3, PaddleX 3.0, PaddlePaddle-GPU |
| **Vector Database** | ChromaDB (local persistence) |
| **Embeddings** | sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`) |
| **TTS Engine** | Edge TTS (async stream) |
| **Fine-tuning** | QLoRA, Unsloth (Colab) |
| **Deployment** | Docker, Kubernetes (`k8s/`), GitHub Actions |

---

## Installation & Quickstart

### Prerequisites
- Python **3.11+**
- Node.js **18+**
- (Optional) Flutter SDK (for mobile Android app)
- (Optional) NVIDIA GPU (CUDA 11.8+) for accelerating PP-OCRv6

### Clone Project
```bash
git clone https://github.com/LeNhan18/ViEng.git
cd ViEng
```

### Backend Setup
1. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the FastAPI development server:
   ```bash
   uvicorn app.main:app --reload
   ```
   Access interactive API docs at `http://localhost:8000/docs`.

### Frontend Setup
1. Install node modules and run in development mode:
   ```bash
   cd frontend
   npm install --legacy-peer-deps
   npm run dev
   ```
2. Open your browser and navigate to `http://localhost:3000`.

### Flutter Mobile Setup (Optional)
```bash
cd androidfrontend
flutter pub get
flutter run
```

---

## Environment Configuration

The backend reads configuration values from a local `.env` file. Copy the example file and modify the keys:
```bash
cp .env.example .env
```

| Variable Name | Description | Default Value |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | API Key for Groq inference provider | |
| `OPENAI_API_KEY` | API Key for OpenAI models | |
| `LOG_LEVEL` | Logging level (`debug`, `info`, `warning`) | `info` |
| `USE_DATABASE` | Enable MySQL database persistence | `false` |
| `DB_HOST` | Host address of MySQL server | `127.0.0.1` |
| `DB_PORT` | Port of MySQL server | `3306` |
| `DB_USER` | MySQL database user name | `root` |
| `DB_PASSWORD` | MySQL database password | |
| `DB_NAME` | MySQL database name | `vieng` |
| `USE_REDIS` | Enable Redis/Redict session caching | `false` |
| `REDIS_HOST` | Redis host address | `127.0.0.1` |
| `REDIS_PORT` | Redis server port | `6379` |
| `PADDLE_PDX_CACHE_HOME` | Model download cache folder for PaddleX/OCR | `E:\AI_CACHE\paddle_ocr` |
| `TEMP` / `TMP` | Temporary directory redirection for PaddleX extractions | `E:\AI_CACHE\paddle_ocr\temp` |

---

## LLM & VLM Providers

ViEng is highly flexible and supports multiple text generation providers:
- **Groq**: Extremely fast inference (Llama-3 models).
- **OpenAI**: High-quality reasoning (GPT-4o).
- **Fine-tuned Local Model**: Access Qwen2.5-7B fine-tuned specifically for TOEIC/IELTS explanations.

Fine-tuned LoRA Adapter link:
- [LeNhan18/ViEng-Qwen2.5-7B-lora](https://huggingface.co/LeNhan18/ViEng-Qwen2.5-7B-lora)

To activate fine-tuned mode, configure in `.env`:
```env
USE_FINETUNED_MODEL=true
HF_MODEL_NAME=LeNhan18/ViEng-Qwen2.5-7B-lora
LLM_PROVIDER=hf_inference # 'hf_inference' (Hugging Face API) or 'hf_local' (local GPU loading)
HF_TOKEN=your_huggingface_token
```

---

## GPU Acceleration & Cache Redirect

For deep layout analysis and table OCR, the backend leverages **PP-OCRv6** & **PP-StructureV3**. 

### GPU Support
Make sure to install the GPU version of PaddlePaddle matching your system's CUDA version. For CUDA 11.8:
```bash
pip install paddlepaddle-gpu==3.0.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/
```

### Cache Redirection
PaddleX downloads several gigabytes of official models (layout detectors, table structurers, formula recognizers). Since Windows system drives (C:) often run out of space, the application automatically redirects all downloads and temp extractions to the **E:** drive (or any custom path specified in `.env`):
```env
PADDLE_PDX_CACHE_HOME=E:\AI_CACHE\paddle_ocr
TEMP=E:\AI_CACHE\paddle_ocr\temp
TMP=E:\AI_CACHE\paddle_ocr\temp
```

---

## API Reference

All backend APIs are prefixed with `/api/v1`.

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :---: |
| `GET` | `/health` | Server health check | No |
| `POST` | `/test/generate` | Generate realistic TOEIC/IELTS questions | No |
| `POST` | `/test/submit` | Submit answers and get Vietnamese feedback + explanations | No |
| `POST` | `/chat` | RAG-guided chatbot (saves to DB and cache if logged in) | Optional |
| `GET` | `/chat/history` | Get persistent chat history | Yes |
| `DELETE` | `/chat/history` | Clear chat history | Yes |
| `POST` | `/chat/ocr` | Upload PDF or image, extract layout + OCR, and chat | Optional |
| `POST` | `/ocr` | Extract structured text/Markdown from PDF or image (debug) | No |
| `POST` | `/translate` | Translate text, extract vocabulary and grammar | No |
| `POST` | `/tts` | Speech synthesis for English text (MP3 stream output) | No |
| `POST` | `/rag/index` | Parse and index local documents into ChromaDB | No |
| `GET` | `/rag/list` | List document chunks in the vector database | No |

---

## Document Parsing & RAG Ingestion

To populate the RAG vector store with custom study material:
1. Place `.txt` (grammar rules, test tips) or `.pdf` (textbooks, scanned exams) files into `data/knowledge_base/`.
2. Run the ingestion endpoint:
   ```bash
   curl -X POST http://localhost:8000/api/v1/rag/index
   ```
3. During indexing, `.pdf` files are parsed using the **PP-StructureV3 GPU pipeline** which converts tables, formulas, and layouts into clean Markdown pages, splitting them indexable chunk-by-chunk for the ChromaDB store.

---

## Fine-tuning Workflow

We use **Qwen2.5-7B** as the base model and fine-tune it with RAG-generated training data:
1. Place source materials in `data/knowledge_base/`.
2. Generate the training dataset locally:
   ```bash
   python scripts/generate_finetune_dataset.py
   ```
   This generates `data/finetune_dataset.jsonl`.
3. Upload the dataset to Google Colab and run the training steps in `FineTune_ViEng.ipynb` using Unsloth.

---

## Project Structure

```
ViEng/
├── app/                  # FastAPI backend
│   ├── api/routes.py     # Endpoint routing
│   ├── core/config.py    # Environment settings
│   ├── db/database.py    # MySQL connection & schemas
│   ├── models/           # SQLAlchemy ORM and Pydantic schemas
│   └── services/         # Business logic
│       ├── ocr_service.py # PP-StructureV3 GPU integration
│       ├── rag_service.py # ChromaDB context indexing & search
│       └── llm_service.py # OpenAI / Groq / HF local model wrapper
├── frontend/             # React web application
│   ├── src/
│   │   ├── pages/        # Home, Chat, Exam, Result, Translate pages
│   │   └── components/   # Chat bubbles, timers, loaders
├── androidfrontend/      # Flutter Android app
├── data/
│   ├── knowledge_base/   # PDF/TXT training data & RAG corpus
│   └── vectorstore/      # ChromaDB storage directory
├── k8s/                  # Kubernetes deployment manifests
├── scripts/              # Dataset generation & tools
└── tests/                # Pytest api tests
```

---

## Roadmap

- [ ] Support TOEIC Listening simulation (Parts 1–4 with audio integration).
- [ ] Add IELTS Writing evaluation (grading grammar, vocabulary, task response).
- [ ] Implement spaced repetition vocabulary card decks.
- [ ] Add student performance analytics & score tracker graphs.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
