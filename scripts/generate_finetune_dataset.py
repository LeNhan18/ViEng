"""
Script sinh dataset fine-tune RAG-augmented cho ViEng.
Dung Groq API (mien phi) de tao 3 loai mau:
  1. TOEIC Part 5 (Incomplete Sentences)
  2. TOEIC Part 6 (Text Completion)
  3. TOEIC Part 7 (Reading Comprehension)
  4. Giai thich dap an theo phong cach thay co Viet (co kem RAG context)

Training data BAO GOM RAG context trong conversation,
de model hoc cach su dung retrieved context khi generate.

Cach chay:
    cd E:/ViEng
    python scripts/generate_finetune_dataset.py --from-kb                    # Sinh tu knowledge_base (max 50 chunk)
    python scripts/generate_finetune_dataset.py --from-kb --max-chunks 100  # Tang so chunk
    python scripts/generate_finetune_dataset.py --from-kb --start 50         # Tiep tuc tu chunk 51
    python scripts/generate_finetune_dataset.py --from-kb --delay 8          # Tang delay neu bi rate limit
    python scripts/generate_finetune_dataset.py --from-kb --questions-only    # Chi cau hoi (30 chunk/phut)
    python scripts/generate_finetune_dataset.py --from-kb --use-ollama        # Ollama local (khong gioi han)
    python scripts/generate_finetune_dataset.py --overwrite                   # Tao lai tu dau

    # Trong .env them GROQ_API_KEY_2, GROQ_API_KEY_3 de tang quota khi bi rate limit
"""

import argparse
import json
import time
import os
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from groq import Groq
from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

OUTPUT_FILE = PROJECT_ROOT / "data" / "finetune_dataset.jsonl"
_llm_client = None
_llm_provider = "groq"
_groq_keys: list[str] = []
_groq_key_index = 0

retriever = None
KB_DIR = PROJECT_ROOT / "data" / "knowledge_base"


def load_kb_chunks() -> list[dict]:
    """Doc .txt va .pdf tu knowledge_base, tra ve danh sach chunk {"content", "source"}."""
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    chunks_out = []
    docs_path = Path(KB_DIR)

    if not docs_path.exists():
        return []

    # Load .txt
    for txt_file in sorted(docs_path.glob("**/*.txt")):
        try:
            loader = TextLoader(str(txt_file), encoding="utf-8")
            docs = loader.load()
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=600,
                chunk_overlap=80,
                separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
            )
            parts = splitter.split_documents(docs)
            for p in parts:
                if p.page_content.strip():
                    chunks_out.append({
                        "content": p.page_content.strip(),
                        "source": txt_file.name,
                    })
        except Exception as e:
            print(f"  [!] Khong doc duoc {txt_file.name}: {e}")

    # Load .pdf
    for pdf_file in sorted(docs_path.glob("**/*.pdf")):
        try:
            loader = PyPDFLoader(str(pdf_file))
            docs = loader.load()
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=600,
                chunk_overlap=80,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            parts = splitter.split_documents(docs)
            for p in parts:
                if p.page_content.strip():
                    chunks_out.append({
                        "content": p.page_content.strip(),
                        "source": pdf_file.name,
                    })
        except Exception as e:
            print(f"  [!] Khong doc duoc {pdf_file.name}: {e}")

    return chunks_out


def init_rag():
    """Khoi tao RAG retriever tu knowledge base (standalone, khong can FastAPI)."""
    global retriever
    from app.services.rag_service import create_standalone_retriever

    print("  Dang khoi tao RAG retriever tu knowledge base...")
    retriever = create_standalone_retriever(
        docs_dir=str(PROJECT_ROOT / "data" / "knowledge_base"),
        persist_dir=str(PROJECT_ROOT / "data" / "vectorstore"),
    )
    if retriever:
        print("  RAG retriever san sang!")
    else:
        print("  [!] Khong the khoi tao RAG (knowledge base trong?). Tiep tuc khong co RAG.")


def retrieve_context(query: str, k: int = 3) -> str:
    """Retrieve context tu knowledge base. Tra ve '' neu khong co retriever."""
    if retriever is None:
        return ""
    try:
        return retriever(query, k=k)
    except Exception:
        return ""


PART5_CONFIGS = [
    {"level": "beginner", "n": 25},
    {"level": "intermediate", "n": 25},
    {"level": "advanced", "n": 25},
]

PART6_CONFIGS = [
    {"level": "beginner", "n_passages": 5},
    {"level": "intermediate", "n_passages": 5},
    {"level": "advanced", "n_passages": 5},
]

PART7_SINGLE_CONFIGS = [
    {"level": "intermediate", "n_passages": 5},
    {"level": "advanced", "n_passages": 5},
]

PART7_MULTI_CONFIGS = [
    {"level": "intermediate", "n_sets": 3},
    {"level": "advanced", "n_sets": 3},
]

GRAMMAR_TOPICS = [
    "present simple vs present continuous",
    "present perfect vs past simple",
    "passive voice",
    "conditional type 1 vs type 2",
    "conditional type 3",
    "relative clauses (who, which, that, whose)",
    "subject-verb agreement",
    "articles (a, an, the)",
    "gerund vs infinitive",
    "comparative and superlative",
    "reported speech",
    "prepositions of time (at, in, on)",
    "prepositions of place (at, in, on)",
    "linking words (however, therefore, moreover)",
    "adjective vs adverb",
    "causative (have/get something done)",
    "phrasal verbs (turn down, carry out, put off)",
    "collocations (make vs do)",
    "countable vs uncountable nouns",
    "modal verbs (must, should, might, could)",
]

SYSTEM_MSG_GENERATE = (
    "Ban la giao vien luyen thi TOEIC chuyen nghiep tai Viet Nam. "
    "Khi duoc cung cap tai lieu tham khao, hay su dung noi dung do de tao cau hoi chinh xac hon. "
    "Luon tra ve JSON hop le."
)

SYSTEM_MSG_EXPLAIN = (
    "Ban la thay giao tieng Anh Viet Nam, giai thich than thien, gan gui, de hieu. "
    "Khi duoc cung cap tai lieu tham khao, hay dua vao do de giai thich chinh xac hon."
)


class GroqAPIError(Exception):
    """Loi API - 401: het key, 429: rate limit, timeout, connection."""
    def __init__(self, msg: str, is_auth: bool = False):
        self.is_auth = is_auth
        super().__init__(msg)


def init_llm(use_ollama: bool = False, ollama_model: str = "qwen2.5:7b") -> None:
    """Khoi tao LLM client: Groq hoac Ollama (local)."""
    global _llm_client, _llm_provider, _groq_keys
    if use_ollama:
        try:
            from openai import OpenAI
            c = OpenAI(base_url="http://localhost:11434/v1/", api_key="ollama")
            globals()["_llm_client"] = c
            globals()["_llm_provider"] = "ollama"
            globals()["_ollama_model"] = ollama_model
            globals()["_groq_keys"] = []
            print(f"  LLM: Ollama - {ollama_model} (local, khong gioi han)")
        except Exception as e:
            raise GroqAPIError(
                f"Khong ket noi Ollama. Chay 'ollama run qwen2.5:7b' truoc. {e}",
                is_auth=False,
            )
    else:
        keys = [
            os.getenv("GROQ_API_KEY"),
            os.getenv("GROQ_API_KEY_2"),
            os.getenv("GROQ_API_KEY_3"),
        ]
        gk = [k for k in keys if k and str(k).strip()]
        if not gk:
            raise GroqAPIError("Khong co GROQ_API_KEY trong .env", is_auth=True)
        globals()["_groq_keys"] = gk
        globals()["_llm_client"] = Groq(api_key=gk[0])
        globals()["_llm_provider"] = "groq"
        globals()["_ollama_model"] = None
        print(f"  LLM: Groq ({len(gk)} key)")


def _rotate_groq_key() -> bool:
    """Doi sang key tiep theo. Tra True neu con key."""
    global _groq_key_index
    keys = globals().get("_groq_keys") or []
    _groq_key_index += 1
    if _groq_key_index < len(keys):
        globals()["_llm_client"] = Groq(api_key=keys[_groq_key_index])
        print(f"    Doi sang key #{_groq_key_index + 1}/{len(keys)}")
        return True
    return False


def call_groq(system_msg: str, user_msg: str, max_tokens: int = 2000, temp: float = 0.35, retries: int = 3) -> str:
    prov = globals().get("_llm_provider") or "groq"
    model = (globals().get("_ollama_model") or "qwen2.5:7b") if prov == "ollama" else "llama-3.3-70b-versatile"
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = globals()["_llm_client"].chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                temperature=temp,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            err_str = str(e).lower()
            if "401" in err_str or "invalid" in err_str or "expired" in err_str or "api_key" in err_str:
                raise GroqAPIError(
                    "GROQ_API_KEY het han hoac sai. Cap nhat .env va thu lai.",
                    is_auth=True,
                ) from e
            if ("429" in err_str or "rate" in err_str) and prov == "groq":
                if _rotate_groq_key():
                    time.sleep(2)
                    continue
                wait = 60 + attempt * 30
                if attempt < retries:
                    print(f"    [429] Rate limit. Cho {wait}s roi thu lai ({attempt+1}/{retries})...")
                    time.sleep(wait)
                else:
                    raise GroqAPIError("Rate limit. Them GROQ_API_KEY_2, _3 vao .env de tang quota.", is_auth=False) from e
                continue
            last_err = e
            if attempt < retries:
                time.sleep(5 + attempt * 5)
    raise GroqAPIError(f"Timeout/Connection: {last_err}", is_auth=False) from last_err


def build_rag_section(context: str) -> str:
    """Tao doan RAG context de chen vao user message trong training data."""
    if not context:
        return ""
    return f"\n\nTai lieu tham khao ngu phap/tu vung:\n---\n{context}\n---\n"


def _clean_json(raw: str) -> str:
    """Loai bo markdown, trim."""
    return raw.strip().strip("`").replace("json\n", "").replace("json", "").strip()


def validate_part5_output(output: str) -> tuple[bool, str]:
    """Parse va validate Part 5 JSON. Tra ve (valid, error_msg)."""
    try:
        cleaned = _clean_json(output)
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    if not isinstance(data, list):
        return False, "Khong phai array"
    valid_labels = {"A", "B", "C", "D"}
    for i, q in enumerate(data):
        if not isinstance(q, dict):
            return False, f"Q{i}: khong phai object"
        opt = q.get("options") or q.get("options_list", [])
        correct = str(q.get("correct_answer", "")).upper().strip()
        if correct not in valid_labels:
            return False, f"Q{i}: correct_answer '{correct}' khong hop le"
        if not isinstance(opt, list) or len(opt) != 4:
            return False, f"Q{i}: options phai co dung 4 phan tu"
    return True, ""


def validate_part6_output(output: str) -> tuple[bool, str]:
    """Parse va validate Part 6 JSON."""
    try:
        cleaned = _clean_json(output)
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    if not isinstance(data, list):
        return False, "Khong phai array"
    valid_labels = {"A", "B", "C", "D"}
    for item in data:
        if not isinstance(item, dict):
            return False, "Item khong phai object"
        qs = item.get("questions") or item.get("items", [])
        if not qs:
            return False, "Thieu questions"
        for j, q in enumerate(qs):
            opt = q.get("options") or q.get("options_list", [])
            correct = str(q.get("correct_answer", "")).upper().strip()
            if correct not in valid_labels:
                return False, f"Q{j}: correct_answer '{correct}' khong hop le"
            if not isinstance(opt, list) or len(opt) != 4:
                return False, f"Q{j}: options phai co 4 phan tu"
    return True, ""


def validate_part7_output(output: str) -> tuple[bool, str]:
    """Parse va validate Part 7 JSON (single/multi)."""
    try:
        cleaned = _clean_json(output)
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    if not isinstance(data, list):
        return False, "Khong phai array"
    valid_labels = {"A", "B", "C", "D"}
    for item in data:
        if not isinstance(item, dict):
            return False, "Item khong phai object"
        qs = item.get("questions") or []
        if not qs:
            return False, "Thieu questions"
        for j, q in enumerate(qs):
            opt = q.get("options") or []
            correct = str(q.get("correct_answer", "")).upper().strip()
            if correct not in valid_labels:
                return False, f"Q{j}: correct_answer '{correct}' khong hop le"
            if not isinstance(opt, list) or len(opt) != 4:
                return False, f"Q{j}: options phai co 4 phan tu"
    return True, ""


def validate_single_question_json(output: str) -> tuple[bool, str]:
    """Validate 1 cau Part 5 dạng {"question","options","correct_answer"}."""
    try:
        cleaned = _clean_json(output)
        q = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    if not isinstance(q, dict):
        return False, "Khong phai object"
    correct = str(q.get("correct_answer", "")).upper().strip()
    if correct not in {"A", "B", "C", "D"}:
        return False, f"correct_answer '{correct}' khong hop le"
    opt = q.get("options") or []
    if not isinstance(opt, list) or len(opt) != 4:
        return False, "options phai co 4 phan tu"
    return True, ""


def gen_part5(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n"]

    rag_context = retrieve_context(
        f"TOEIC Part 5 grammar tenses word forms prepositions {level}", k=3
    )
    rag_section = build_rag_section(rag_context)

    instruction = (
        f"Tao {n} cau hoi TOEIC Reading Part 5 (Incomplete Sentences) trinh do {level}."
        f"{rag_section}"
    )

    system_msg = (
        f"{SYSTEM_MSG_GENERATE} "
        "Tao cau hoi Part 5 dung format chuan TOEIC that. "
        "Moi cau la 1 cau tieng Anh co 1 cho trong (___), 4 dap an A, B, C, D. "
        "Chu de: cong viec, email, hop dong, kinh doanh, nhan su. "
        "Kiem tra ngu phap (thi, dang tu, gioi tu) hoac tu vung. "
        'Tra ve JSON array: [{"id": 1, "content": "The manager ___ the report before the meeting.", '
        '"options": ["A. review", "B. reviewed", "C. reviewing", "D. reviews"], "correct_answer": "B"}]. '
        "Chi tra ve JSON, khong them text."
    )

    try:
        output = call_groq(system_msg, instruction, max_tokens=4000, temp=0.35)
        valid, err = validate_part5_output(output)
        if not valid:
            print(f"    [!] Part5 validate fail: {err}. Bo qua.")
            return []
        return [{"instruction": instruction, "output": output, "system": SYSTEM_MSG_GENERATE}]
    except Exception as e:
        print(f"  [!] Part5 error: {e}")
        return []


def gen_part6(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n_passages"]

    rag_context = retrieve_context(
        f"TOEIC Part 6 connectors conjunctions text completion grammar {level}", k=3
    )
    rag_section = build_rag_section(rag_context)

    instruction = (
        f"Tao {n} doan van TOEIC Reading Part 6 (Text Completion) trinh do {level}."
        f"{rag_section}"
    )

    system_msg = (
        f"{SYSTEM_MSG_GENERATE} "
        "Tao doan van Part 6 dung format chuan TOEIC that. "
        "Moi doan la 1 email/memo/thong bao (100-150 tu) co dung 4 cho trong danh so (1), (2), (3), (4). "
        "Moi cho trong co 4 dap an A, B, C, D. "
        "Co the hoi: dien tu, dien cum tu, hoac dien ca cau phu hop ngu canh. "
        'Tra ve JSON array: [{"passage": "Dear Mr. Smith,...(1)___...(2)___...", '
        '"questions": [{"id": 1, "content": "(1)", "options": ["A. accepted", "B. accepting", "C. accept", "D. acceptable"], "correct_answer": "A"}, ...]}]. '
        "Chi tra ve JSON, khong them text."
    )

    try:
        output = call_groq(system_msg, instruction, max_tokens=3000, temp=0.35)
        valid, err = validate_part6_output(output)
        if not valid:
            print(f"    [!] Part6 validate fail: {err}. Bo qua.")
            return []
        return [{"instruction": instruction, "output": output, "system": SYSTEM_MSG_GENERATE}]
    except Exception as e:
        print(f"  [!] Part6 error: {e}")
        return []


def gen_part7_single(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n_passages"]

    rag_context = retrieve_context(
        f"TOEIC Part 7 reading comprehension vocabulary business {level}", k=2
    )
    rag_section = build_rag_section(rag_context)

    instruction = (
        f"Tao {n} bai doc TOEIC Reading Part 7 Single Passage trinh do {level}."
        f"{rag_section}"
    )

    system_msg = (
        f"{SYSTEM_MSG_GENERATE} "
        "Tao bai doc Part 7 Single Passage dung format chuan TOEIC that. "
        "Moi bai la 1 doan van (email, quang cao, thong bao, bai bao) dai 150-250 tu. "
        "Moi bai co 2-4 cau hoi: y chinh, chi tiet, suy luan, tu dong nghia, muc dich nguoi viet. "
        'Tra ve JSON array: [{"passages": ["Dear Employees,..."], '
        '"questions": [{"id": 1, "content": "What is the purpose of the email?", '
        '"options": ["A. To announce a policy change", "B. ...", "C. ...", "D. ..."], '
        '"correct_answer": "A"}, ...]}]. '
        "Chi tra ve JSON, khong them text."
    )

    try:
        output = call_groq(system_msg, instruction, max_tokens=4000, temp=0.35)
        valid, err = validate_part7_output(output)
        if not valid:
            print(f"    [!] Part7 single validate fail: {err}. Bo qua.")
            return []
        return [{"instruction": instruction, "output": output, "system": SYSTEM_MSG_GENERATE}]
    except Exception as e:
        print(f"  [!] Part7 single error: {e}")
        return []


def gen_part7_multi(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n_sets"]

    rag_context = retrieve_context(
        f"TOEIC Part 7 multiple passages vocabulary business communication {level}", k=2
    )
    rag_section = build_rag_section(rag_context)

    instruction = (
        f"Tao {n} bo TOEIC Reading Part 7 Multiple Passages trinh do {level}."
        f"{rag_section}"
    )

    system_msg = (
        f"{SYSTEM_MSG_GENERATE} "
        "Tao bo doc Part 7 Multiple Passages dung format chuan TOEIC that. "
        "Moi bo gom 2-3 doan van lien quan (email + reply, quang cao + review, memo + schedule). "
        "Moi bo co 5 cau hoi, yeu cau lien ket thong tin giua cac doan. "
        'Tra ve JSON array: [{"passages": ["From: john@co.com\\n...", "From: sarah@co.com\\n..."], '
        '"questions": [{"id": 1, "content": "What does John suggest?", '
        '"options": ["A. ...", "B. ...", "C. ...", "D. ..."], '
        '"correct_answer": "A"}, ... (5 cau hoi)]}]. '
        "Chi tra ve JSON, khong them text."
    )

    try:
        output = call_groq(system_msg, instruction, max_tokens=4000, temp=0.35)
        valid, err = validate_part7_output(output)
        if not valid:
            print(f"    [!] Part7 multi validate fail: {err}. Bo qua.")
            return []
        return [{"instruction": instruction, "output": output, "system": SYSTEM_MSG_GENERATE}]
    except Exception as e:
        print(f"  [!] Part7 multi error: {e}")
        return []


def gen_explanation(topic: str) -> list[dict]:
    """Sinh 1 cau hoi Part 5 + giai thich RAG-augmented theo phong cach thay co Viet."""
    samples = []

    rag_context = retrieve_context(f"English grammar rules {topic} examples TOEIC", k=3)
    rag_section = build_rag_section(rag_context)

    instruction_q = (
        f"Tao 1 cau hoi TOEIC Part 5 ve chu de ngu phap: {topic}. "
        "Cau hoi dang dien vao cho trong, 4 dap an A/B/C/D. "
        f"{rag_section}"
        'Tra ve JSON: {"question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "B"}. '
        "Chi tra ve JSON."
    )

    try:
        question_json = call_groq(
            SYSTEM_MSG_GENERATE,
            instruction_q,
            max_tokens=500,
            temp=0.35,
        )

        valid, err = validate_single_question_json(question_json)
        if not valid:
            print(f"    [!] Explanation question validate fail ({topic}): {err}. Bo qua.")
            return []

        try:
            cleaned = _clean_json(question_json)
            q_data = json.loads(cleaned)
            question_text = q_data.get("question", "")
            correct = q_data.get("correct_answer", "")
            options = q_data.get("options", [])
        except json.JSONDecodeError:
            question_text = question_json
            correct = ""
            options = []

        instruction_explain = (
            f"Giai thich cau hoi TOEIC sau cho hoc sinh Viet Nam:\n"
            f"Cau hoi: {question_text}\n"
            f"Dap an: {', '.join(options)}\n"
            f"Dap an dung: {correct}\n"
            f"Chu de ngu phap: {topic}\n"
            f"{rag_section}\n"
            "Hay giai thich theo phong cach thay co Viet Nam: than thien, gan gui, "
            "dung vi du doi thuong, co meo ghi nho. "
            "Khi co tai lieu tham khao, hay trich dan quy tac/vi du tu do. "
            "Bat dau bang 'Em oi' hoac tuong tu."
        )

        explanation = call_groq(
            SYSTEM_MSG_EXPLAIN,
            instruction_explain,
            max_tokens=800,
            temp=0.4,
        )

        samples.append({"instruction": instruction_q, "output": question_json, "system": SYSTEM_MSG_GENERATE})
        samples.append({"instruction": instruction_explain, "output": explanation, "system": SYSTEM_MSG_EXPLAIN})

    except Exception as e:
        print(f"  [!] Explanation error ({topic}): {e}")

    return samples


def gen_from_chunk(chunk: dict, n_questions: int = 2, questions_only: bool = False) -> list[dict]:
    """Sinh cau hoi (+ giai thich neu khong questions_only) dua vao noi dung chunk."""
    content = chunk.get("content", "")
    source = chunk.get("source", "N/A")
    if not content or len(content) < 50:
        return []

    doc_section = f"\n\n--- Tai lieu (nguon: {source}) ---\n{content}\n--- Het tai lieu ---\n"

    instruction_q = (
        f"Dua vao tai lieu duoi day (co the bo sung kien thuc ben ngoai neu can).\n"
        f"{doc_section}\n"
        f"Tao {n_questions} cau hoi TOEIC Part 5 (Incomplete Sentences) dua tren quy tac/vi du trong tai lieu. "
        "Moi cau 1 cho trong, 4 dap an A/B/C/D. "
        'Tra ve JSON array: [{"id": 1, "content": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "B"}, ...]. '
        "Chi tra ve JSON."
    )

    samples = []
    try:
        output = call_groq(SYSTEM_MSG_GENERATE, instruction_q, max_tokens=2000, temp=0.35)
        valid, err = validate_part5_output(output)
        if not valid:
            print(f"    [!] Chunk ({source}) validate fail: {err}. Bo qua.")
            return []

        samples.append({"instruction": instruction_q, "output": output, "system": SYSTEM_MSG_GENERATE})
        if questions_only:
            return samples
        time.sleep(2)

        # Parse va sinh giai thich cho tung cau
        try:
            cleaned = _clean_json(output)
            arr = json.loads(cleaned)
            if not isinstance(arr, list):
                arr = [arr]
            for q in arr[:2]:  # Toi da 2 giai thich
                question_text = q.get("content", "")
                correct = q.get("correct_answer", "")
                options = q.get("options", [])
                instruction_explain = (
                    f"Giai thich cau hoi TOEIC sau cho hoc sinh Viet Nam, dua vao tai lieu tham khao:\n"
                    f"{doc_section}\n"
                    f"Cau hoi: {question_text}\n"
                    f"Dap an: {', '.join(options)}\n"
                    f"Dap an dung: {correct}\n"
                    "Hay giai thich theo phong cach thay co Viet Nam: than thien, gan gui, "
                    "dung vi du doi thuong, co meo ghi nho. Bat dau bang 'Em oi' hoac tuong tu."
                )
                explanation = call_groq(
                    SYSTEM_MSG_EXPLAIN,
                    instruction_explain,
                    max_tokens=800,
                    temp=0.4,
                )
                time.sleep(2)
                samples.append({
                    "instruction": instruction_explain,
                    "output": explanation,
                    "system": SYSTEM_MSG_EXPLAIN,
                })
        except json.JSONDecodeError:
            pass

    except GroqAPIError:
        raise
    except Exception as e:
        print(f"  [!] Chunk ({source}) error: {e}")
        return []

    return samples


def to_chat_format(samples: list[dict]) -> list[dict]:
    """Chuyen sang chat format voi system message (de model hoc cach xu ly RAG context)."""
    chat_samples = []
    for s in samples:
        conversation = {"conversations": []}
        if s.get("system"):
            conversation["conversations"].append({"role": "system", "content": s["system"]})
        conversation["conversations"].append({"role": "user", "content": s["instruction"]})
        conversation["conversations"].append({"role": "assistant", "content": s["output"]})
        chat_samples.append(conversation)
    return chat_samples


def main():
    parser = argparse.ArgumentParser(description="Sinh dataset fine-tune ViEng")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Tao lai tu dau, ghi de file finetune_dataset.jsonl (mac dinh: cong don vao file cu)",
    )
    parser.add_argument(
        "--from-kb",
        action="store_true",
        help="Sinh du lieu DUA VAO cac file .txt va .pdf trong data/knowledge_base (bo qua tao generic)",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=50,
        help="Khi --from-kb: gioi han so chunk xu ly (mac dinh 50, tong 791). Tang key Groq co gioi han.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Khi --from-kb: bat dau tu chunk thu N (de tiep tuc khi bi dung giua chung)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="So giay cho giua moi chunk (mac dinh 5, tang len neu bi rate limit)",
    )
    parser.add_argument(
        "--questions-only",
        action="store_true",
        help="Chi sinh cau hoi, khong sinh giai thich (1 call/chunk -> ~30 chunk/phut voi Groq)",
    )
    parser.add_argument(
        "--use-ollama",
        action="store_true",
        help="Dung Ollama local - khong gioi han rate",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default="qwen2.5:7b",
        help="Model Ollama (mac dinh qwen2.5:7b). Ban co gemma3:4b thi dung --ollama-model gemma3:4b",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("ViEng - Sinh dataset fine-tune LLM (RAG-augmented)")
    try:
        init_llm(use_ollama=args.use_ollama, ollama_model=args.ollama_model)
    except GroqAPIError as e:
        print(f"[!] {e}")
        return
    if args.from_kb:
        print("Che do: TU FILE TRONG KNOWLEDGE_BASE (--from-kb)")
    else:
        print("TOEIC Part 5/6/7 + Giai thich")
    if args.overwrite:
        print("Ghi de: TAO LAI TU DAU (--overwrite)")
    else:
        print("Ghi: CONG DON vao file cu")
    print("=" * 60)

    all_samples = []

    if args.from_kb:
        chunks = load_kb_chunks()
        if not chunks:
            print("[!] Khong tim thay file .txt hoac .pdf trong data/knowledge_base")
            return
        start = max(0, args.start)
        end = min(start + args.max_chunks, len(chunks))
        to_process = chunks[start:end]
        print(f"  Tim thay {len(chunks)} chunk. Xu ly {len(to_process)} chunk (tu #{start+1} den #{end})")
        print(f"  Tip: --max-chunks 50 --start {end} de tiep tuc lan sau")
        for i, chunk in enumerate(to_process, start + 1):
            src = chunk.get("source", "?")
            print(f"  [{i}/{len(chunks)}] Chunk tu {src}...")
            try:
                samples = gen_from_chunk(chunk, n_questions=2, questions_only=args.questions_only)
                all_samples.extend(samples)
            except GroqAPIError as ex:
                print(f"\n[!] DUNG LAI: {ex}")
                if ex.is_auth:
                    print("    Cap nhat GROQ_API_KEY trong file .env va chay lai.")
                if all_samples:
                    chat = to_chat_format(all_samples)
                    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                        for s in chat:
                            f.write(json.dumps(s, ensure_ascii=False) + "\n")
                    print(f"    Da luu {len(chat)} mau vao {OUTPUT_FILE}")
                return
            time.sleep(args.delay)
    else:
        init_rag()
        tasks = []
        for c in PART5_CONFIGS:
            tasks.append(("Part 5", c["level"], lambda cfg=c: gen_part5(cfg)))
        for c in PART6_CONFIGS:
            tasks.append(("Part 6", c["level"], lambda cfg=c: gen_part6(cfg)))
        for c in PART7_SINGLE_CONFIGS:
            tasks.append(("Part 7 Single", c["level"], lambda cfg=c: gen_part7_single(cfg)))
        for c in PART7_MULTI_CONFIGS:
            tasks.append(("Part 7 Multi", c["level"], lambda cfg=c: gen_part7_multi(cfg)))
        for topic in GRAMMAR_TOPICS:
            tasks.append(("Explanation", topic, lambda t=topic: gen_explanation(t)))

        total = len(tasks)
        for i, (label, detail, fn) in enumerate(tasks, 1):
            print(f"  [{i}/{total}] {label} - {detail}...")
            samples = fn()
            all_samples.extend(samples)
            time.sleep(2)

    chat_samples = to_chat_format(all_samples)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    file_mode = "w" if args.overwrite else "a"
    existing_count = 0
    if OUTPUT_FILE.exists() and not args.overwrite:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_count = sum(1 for line in f if line.strip())

    with open(OUTPUT_FILE, file_mode, encoding="utf-8") as f:
        for sample in chat_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    new_count = len(chat_samples)
    total_count = new_count if args.overwrite else existing_count + new_count
    if args.from_kb:
        rag_status = "TU FILE KNOWLEDGE_BASE"
    else:
        rag_status = "CO RAG context" if retriever else "KHONG CO RAG"
    print(f"\n{'=' * 60}")
    print(f"Mau moi sinh: {new_count} ({rag_status})")
    print(f"Tong so mau: {total_count}" + (" (tao lai)" if args.overwrite else " (cong don)"))
    print(f"Da luu vao: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
