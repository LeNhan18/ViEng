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
  <img src="https://img.shields.io/badge/GitHub%20Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
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
- [Architecture (High-level)](#architecture-high-level)
- [Tech Stack](#tech-stack)
- [Quickstart (Local)](#quickstart-local)
- [Configuration](#configuration)
- [LLM Providers](#llm-providers)
- [Docker](#docker)
- [CI/CD](#cicd)
- [Kubernetes](#kubernetes)
- [API Reference](#api-reference)
- [Knowledge Base (RAG)](#knowledge-base-rag)
- [Fine-tuning](#fine-tuning)
- [Project Structure](#project-structure)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

**ViEng** is an AI-assisted English exam preparation platform tailored for Vietnamese learners. It provides a **web app** (React) and an optional **mobile app** (Flutter/Android), powered by a **RAG (Retrieval-Augmented Generation)** pipeline and multiple LLM backends.

The platform focuses on:

- Generating TOEIC/IELTS-style practice content
- Explaining answers with Vietnamese-teacher style guidance
- Chat-based Q&A grounded in a curated knowledge base
- AI translation with vocabulary + grammar notes and optional TTS pronunciation

---

## Key Features

- **TOEIC Reading practice**:
  - Part 5 — Incomplete Sentences
  - Part 6 — Text Completion
  - Part 7 — Single & Multiple Passages
- **Answer explanations** tailored by part (sentence-level vs passage-level reasoning)
- **Chatbot with RAG** (grounded responses + source hints)
- **AI translation** (EN↔VI) with:
  - key vocabulary extraction
  - grammar notes
  - optional **TTS pronunciation** (Edge TTS) for VI→EN output
- **Knowledge base ingestion** from `.txt` and `.pdf`

---

## Architecture (High-level)

At runtime, the system looks like:

- **Frontend (React/Vite)** calls the **FastAPI backend**
- Backend optionally performs **RAG retrieval** (ChromaDB vector store)
- Backend calls an LLM provider (Groq / OpenAI / Fine-tuned model via Hugging Face)

---

## Tech Stack

| Layer | Technology |
|------|------------|
| **Backend** | Python 3.11+, FastAPI |
| **Web** | React, Vite, TailwindCSS |
| **Mobile (optional)** | Flutter (Android) |
| **LLM** | Groq / OpenAI / Hugging Face (fine-tuned) |
| **RAG** | LangChain, ChromaDB |
| **Embeddings** | sentence-transformers (multilingual) |
| **TTS** | edge-tts |
| **Fine-tuning** | QLoRA, Unsloth (Colab) |
| **Packaging/Deploy** | Docker, Kubernetes (`k8s/`), GitHub Actions (CI + GHCR) |

---

## Quickstart (Local)

### Prerequisites

- Python **3.11+**
- Node.js **18+** (for web)
- (Optional) Flutter SDK (for Android)
- LLM API key: Groq or OpenAI (unless you use the fine-tuned HF option)

### Clone

```bash
git clone https://github.com/LeNhan18/ViEng.git
cd ViEng
```

### Backend

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`

### Web (React)

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

Web app: `http://localhost:3000`

> The Vite dev server proxies `/api` to `http://localhost:8000`.

### Mobile (optional)

```bash
cd androidfrontend
flutter pub get
flutter run
```

---

## Configuration

The backend reads environment variables from `.env`.

If you have an example file, copy it first:

```bash
cp .env.example .env
```

Common variables:

| Variable | Description |
|---------|-------------|
| `GROQ_API_KEY` | Groq API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `LOG_LEVEL` | Logging level (e.g. `info`, `debug`) |

---

## LLM Providers

ViEng supports multiple LLM backends:

- **Groq** (fast hosted inference)
- **OpenAI**
- **Fine-tuned model on Hugging Face** (recommended for “fine-tune mode” in deployments)

Fine-tuned model link:
- [LeNhan18/ViEng-Qwen2.5-7B-lora](https://huggingface.co/LeNhan18/ViEng-Qwen2.5-7B-lora)

Enable fine-tuned mode:

```env
USE_FINETUNED_MODEL=true
HF_MODEL_NAME=LeNhan18/ViEng-Qwen2.5-7B-lora

# Choose how to use the fine-tuned model:
# - hf_inference: Hugging Face Inference API (lightweight, deploy-friendly)
# - hf_local: load locally with transformers/torch (heavy; requires GPU/extra deps)
LLM_PROVIDER=hf_inference

# Optional token (public models may work without it depending on rate limits)
HF_TOKEN=
```

Per-request provider override:

- Frontend can send `llm_provider` for `/test/generate`, `/chat`, and `/translate`
- Supported values: `groq`, `openai`, `hf_inference`, `hf_local`, `auto`

---

## Docker

### Backend (FastAPI)

```bash
docker build -t vieng-backend .
docker run --rm -p 8000:8000 --env-file .env vieng-backend
```

### Frontend (Vite build + Nginx)

```bash
docker build -t vieng-frontend ./frontend
docker run --rm -p 3000:80 vieng-frontend
```

---

## CI/CD

This repository includes GitHub Actions workflows:

- **CI**: `.github/workflows/ci.yml`
  - Backend: installs deps and runs `pytest`
  - Frontend: installs deps and runs `npm run build`
- **Docker build & push (GHCR)**: `.github/workflows/docker.yml`
  - Builds and pushes backend/frontend images to `ghcr.io`

Image naming:

- `ghcr.io/<owner>/<repo>-backend:<tag>`
- `ghcr.io/<owner>/<repo>-frontend:<tag>`

> Note: the workflow pushes images, but does not automatically deploy to a Kubernetes cluster (no `kubectl apply` step yet).

---

## Kubernetes

Sample manifests live in `k8s/`:

- `namespace.yaml`
- `backend-deployment.yaml`, `backend-service.yaml`
- `frontend-deployment.yaml`, `frontend-service.yaml`
- `ingress.yaml` (routes `/api` → backend, `/` → frontend)

Apply:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

### Secrets (API keys)

Create a secret in the `vieng` namespace:

```bash
kubectl -n vieng create secret generic vieng-secrets \
  --from-literal=GROQ_API_KEY="..." \
  --from-literal=OPENAI_API_KEY="..." \
  --from-literal=USE_FINETUNED_MODEL="false" \
  --from-literal=HF_MODEL_NAME="" \
  --from-literal=LLM_PROVIDER="hf_inference" \
  --from-literal=HF_TOKEN=""
```

Security note: **Never commit secrets to git.** Use GitHub Secrets / Kubernetes Secrets.

---

## API Reference

Base prefix: `/api/v1`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/test/generate` | Generate TOEIC/IELTS questions (TOEIC Reading supports Part 5/6/7 formats) |
| `POST` | `/test/submit` | Submit answers and get feedback + explanations |
| `POST` | `/chat` | RAG-grounded chat |
| `POST` | `/translate` | EN↔VI translation + vocabulary + grammar notes |
| `POST` | `/tts` | Text-to-speech (English) |
| `POST` | `/rag/index` | (Re)index knowledge base into Chroma |
| `GET` | `/rag/list` | List stored chunks (debug/inspection) |
| `POST` | `/rag/search` | Search knowledge base |

---

## Knowledge Base (RAG)

Place documents into `data/knowledge_base/`:

| Format | Notes |
|--------|------|
| `.txt` | Grammar, vocabulary, strategies — UTF-8 |
| `.pdf` | TOEIC/IELTS materials (parsed by `pypdf`) |

Index:

```bash
curl -X POST http://localhost:8000/api/v1/rag/index
```

---

## Fine-tuning

ViEng includes a fine-tuning workflow for **Qwen2.5-7B** using **RAG-augmented** training data (Colab/T4):

1. Ensure `data/knowledge_base/` contains `.txt` / `.pdf` documents
2. Generate dataset: `python scripts/generate_finetune_dataset.py`
3. Upload `data/finetune_dataset.jsonl` to Colab
4. Run `FineTune_ViEng.ipynb`

Trained adapter:
- [LeNhan18/ViEng-Qwen2.5-7B-lora](https://huggingface.co/LeNhan18/ViEng-Qwen2.5-7B-lora)

---

## Project Structure

```
ViEng/
├── app/                  # FastAPI backend
│   ├── main.py
│   ├── api/routes.py
│   ├── core/config.py
│   ├── models/schemas.py
│   └── services/
│       ├── llm_service.py
│       └── rag_service.py
├── frontend/             # React web app
│   └── src/
│       ├── pages/        # Home, Exam, Result, Chat, Translate
│       └── components/
├── androidfrontend/      # Flutter Android app (optional)
├── data/
│   ├── knowledge_base/   # .txt, .pdf
│   └── vectorstore/      # ChromaDB persistence
├── k8s/                  # Kubernetes manifests (optional deployment)
├── scripts/
└── tests/
```

---

## Roadmap

- TOEIC Listening (Part 1–4)
- IELTS Reading/Writing enhancements
- Learning progress tracking and sessions

---

## License

MIT License — see [LICENSE](LICENSE).
