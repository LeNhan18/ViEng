"""
Script sinh dataset fine-tune cho ViEng.
Dung Groq API (mien phi) de tao 3 loai mau:
  1. TOEIC Part 5 (Incomplete Sentences)
  2. TOEIC Part 6 (Text Completion)
  3. TOEIC Part 7 (Reading Comprehension)
  4. Giai thich dap an theo phong cach thay co Viet

Cach chay:
    cd E:/ViEng
    python scripts/generate_finetune_dataset.py
"""

import json
import time
import os
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from groq import Groq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

client = Groq(api_key=os.getenv("GROQ_API_KEY"))
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "finetune_dataset.jsonl"


PART5_CONFIGS = [
    {"level": "beginner", "n": 5},
    {"level": "intermediate", "n": 5},
    {"level": "advanced", "n": 5},
]

PART6_CONFIGS = [
    {"level": "beginner", "n_passages": 1},
    {"level": "intermediate", "n_passages": 1},
    {"level": "advanced", "n_passages": 1},
]

PART7_SINGLE_CONFIGS = [
    {"level": "intermediate", "n_passages": 1},
    {"level": "advanced", "n_passages": 1},
]

PART7_MULTI_CONFIGS = [
    {"level": "intermediate", "n_sets": 1},
    {"level": "advanced", "n_sets": 1},
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


def call_groq(system_msg: str, user_msg: str, max_tokens: int = 2000, temp: float = 0.8) -> str:
    resp = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=temp,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()


def gen_part5(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n"]

    instruction = f"Tao {n} cau hoi TOEIC Reading Part 5 (Incomplete Sentences) trinh do {level}."

    system_msg = (
        "Ban la giao vien luyen thi TOEIC giàu kinh nghiem tai Viet Nam. "
        "Tao cau hoi Part 5 dung format chuan TOEIC that. "
        "Moi cau la 1 cau tieng Anh co 1 cho trong (___), 4 dap an A, B, C, D. "
        "Chu de: cong viec, email, hop dong, kinh doanh, nhan su. "
        "Kiem tra ngu phap (thi, dang tu, gioi tu) hoac tu vung. "
        'Tra ve JSON array: [{"id": 1, "content": "The manager ___ the report before the meeting.", '
        '"options": ["A. review", "B. reviewed", "C. reviewing", "D. reviews"], "correct_answer": "B"}]. '
        "Chi tra ve JSON, khong them text."
    )

    try:
        output = call_groq(system_msg, instruction)
        return [{"instruction": instruction, "output": output}]
    except Exception as e:
        print(f"  [!] Part5 error: {e}")
        return []


def gen_part6(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n_passages"]

    instruction = f"Tao {n} doan van TOEIC Reading Part 6 (Text Completion) trinh do {level}."

    system_msg = (
        "Ban la giao vien luyen thi TOEIC giàu kinh nghiem tai Viet Nam. "
        "Tao doan van Part 6 dung format chuan TOEIC that. "
        "Moi doan la 1 email/memo/thong bao (100-150 tu) co dung 4 cho trong danh so (1), (2), (3), (4). "
        "Moi cho trong co 4 dap an A, B, C, D. "
        "Co the hoi: dien tu, dien cum tu, hoac dien ca cau phu hop ngu canh. "
        'Tra ve JSON array: [{"passage": "Dear Mr. Smith,...(1)___...(2)___...", '
        '"questions": [{"id": 1, "content": "(1)", "options": ["A. accepted", "B. accepting", "C. accept", "D. acceptable"], "correct_answer": "A"}, ...]}]. '
        "Chi tra ve JSON, khong them text."
    )

    try:
        output = call_groq(system_msg, instruction, max_tokens=3000)
        return [{"instruction": instruction, "output": output}]
    except Exception as e:
        print(f"  [!] Part6 error: {e}")
        return []


def gen_part7_single(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n_passages"]

    instruction = f"Tao {n} bai doc TOEIC Reading Part 7 Single Passage trinh do {level}."

    system_msg = (
        "Ban la giao vien luyen thi TOEIC giàu kinh nghiem tai Viet Nam. "
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
        output = call_groq(system_msg, instruction, max_tokens=4000)
        return [{"instruction": instruction, "output": output}]
    except Exception as e:
        print(f"  [!] Part7 single error: {e}")
        return []


def gen_part7_multi(config: dict) -> list[dict]:
    level = config["level"]
    n = config["n_sets"]

    instruction = f"Tao {n} bo TOEIC Reading Part 7 Multiple Passages trinh do {level}."

    system_msg = (
        "Ban la giao vien luyen thi TOEIC giàu kinh nghiem tai Viet Nam. "
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
        output = call_groq(system_msg, instruction, max_tokens=4000)
        return [{"instruction": instruction, "output": output}]
    except Exception as e:
        print(f"  [!] Part7 multi error: {e}")
        return []


def gen_explanation(topic: str) -> list[dict]:
    """Sinh 1 cau hoi Part 5 + giai thich theo phong cach thay co Viet."""
    samples = []

    instruction_q = (
        f"Tao 1 cau hoi TOEIC Part 5 ve chu de ngu phap: {topic}. "
        "Cau hoi dang dien vao cho trong, 4 dap an A/B/C/D. "
        'Tra ve JSON: {"question": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "correct_answer": "B"}. '
        "Chi tra ve JSON."
    )

    try:
        question_json = call_groq(
            "Ban la giao vien luyen thi TOEIC Viet Nam.",
            instruction_q,
            max_tokens=500,
        )

        try:
            cleaned = question_json.strip("`").replace("json\n", "").replace("json", "")
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
            f"Chu de ngu phap: {topic}\n\n"
            "Hay giai thich theo phong cach thay co Viet Nam: than thien, gan gui, "
            "dung vi du doi thuong, co meo ghi nho. "
            "Bat dau bang 'Em oi' hoac tuong tu."
        )

        explanation = call_groq(
            "Ban la thay giao tieng Anh Viet Nam, giai thich than thien, gan gui, de hieu.",
            instruction_explain,
            max_tokens=800,
            temp=0.7,
        )

        samples.append({"instruction": instruction_q, "output": question_json})
        samples.append({"instruction": instruction_explain, "output": explanation})

    except Exception as e:
        print(f"  [!] Explanation error ({topic}): {e}")

    return samples


def to_chat_format(samples: list[dict]) -> list[dict]:
    return [
        {
            "conversations": [
                {"role": "user", "content": s["instruction"]},
                {"role": "assistant", "content": s["output"]},
            ]
        }
        for s in samples
    ]


def main():
    print("=" * 60)
    print("ViEng - Sinh dataset fine-tune LLM (TOEIC Part 5/6/7)")
    print("=" * 60)

    all_samples = []
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

    existing_count = 0
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing_count = sum(1 for line in f if line.strip())

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for sample in chat_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    new_count = len(chat_samples)
    total_count = existing_count + new_count
    print(f"\n{'=' * 60}")
    print(f"Mau moi sinh: {new_count}")
    print(f"Tong so mau (cong don): {total_count}")
    print(f"Da luu vao: {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
