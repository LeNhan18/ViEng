"""
Tai dataset TOEIC / tieng Anh tu Hugging Face, chuyen sang finetune_dataset.jsonl.
Dung khi khong sinh duoc bang LLM (Groq/Ollama).

Chay:
    python scripts/download_toeic_dataset.py
    python scripts/download_toeic_dataset.py --overwrite
    pip install datasets
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "data" / "finetune_dataset.jsonl"

# (repo_id, split) — thu lan luot neu dataset ton tai
HF_SOURCES = [
    ("dddodddiiddoddo/TOEIC_problem", "train"),
    ("cuongtm/Toeic_hacker_vol3", "train"),
    ("cuongtm/hacker_toeic_RC", "train"),
    ("nggiabao19/toeic-tutor-v1", "train"),
    ("kknono668/toeic-vocab-tw", "train"),
]


def to_chat(instruction: str, output: str) -> dict:
    return {
        "conversations": [
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": output},
        ]
    }


def _get_first(row: dict, keys: list[str]):
    for k in keys:
        if k in row and row[k] is not None:
            return row[k]
    return None


def _normalize_options(opts) -> list[str]:
    if opts is None:
        return []
    if isinstance(opts, list):
        out = []
        for o in opts[:4]:
            if isinstance(o, dict):
                t = o.get("text") or o.get("content") or str(o)
            else:
                t = str(o).strip()
            if t:
                out.append(t)
        return out
    if isinstance(opts, str):
        for sep in [";", "|", "\n"]:
            if sep in opts:
                return [x.strip() for x in opts.split(sep) if x.strip()][:4]
        return [opts.strip()] if opts.strip() else []
    return []


def _normalize_answer(ans, n_opts: int) -> str:
    if ans is None:
        return "A"
    s = str(ans).strip().upper()
    if s in ("A", "B", "C", "D"):
        return s
    if s.isdigit():
        i = int(s)
        if 0 <= i < n_opts:
            return "ABCD"[i]
        if 1 <= i <= 4 and i <= n_opts:
            return "ABCD"[i - 1]
    # chuoi dung voi mot option
    return "A"


def row_to_sample(row: dict) -> tuple[str, str] | None:
    """Tra ve (instruction, output_json_str) hoac None."""
    q = _get_first(row, [
        "question", "Question", "sentence", "Sentence", "stem",
        "content", "text", "prompt", "question_text",
    ])
    if not q:
        return None
    q = str(q).strip()
    if len(q) < 10:
        return None

    opts = _get_first(row, [
        "options", "Options", "choices", "Choices", "answer_choices",
        "option_a",  # vocab dataset co the khac
    ])
    if opts is None and "option_a" in row:
        opts = [
            row.get("option_a", ""),
            row.get("option_b", ""),
            row.get("option_c", ""),
            row.get("option_d", ""),
        ]
    opts = _normalize_options(opts)
    if len(opts) < 2:
        return None

    ans = _get_first(row, [
        "answer", "Answer", "correct_answer", "correct", "label",
        "key", "gold", "target",
    ])
    labels = "ABCD"[: len(opts)]
    correct = _normalize_answer(ans, len(opts))

    opt_lines = [f"{l}. {o}" for l, o in zip(labels, opts)]
    opt_str = " ".join(opt_lines)
    inst = (
        f"Tao 1 cau hoi TOEIC Part 5 tu de sau:\nCau: {q}\nDap an: {opt_str}"
    )
    out = json.dumps(
        {
            "id": 1,
            "content": q,
            "options": opt_lines,
            "correct_answer": correct if correct in labels else labels[0],
        },
        ensure_ascii=False,
    )
    return inst, out


def load_one_dataset(repo_id: str, split: str) -> tuple[int, list[tuple[str, str]]]:
    from datasets import load_dataset

    ds = load_dataset(repo_id, split=split, trust_remote_code=True)
    count = 0
    rows = []
    if hasattr(ds, "__iter__"):
        for row in ds:
            rows.append(row)
    else:
        rows = list(ds)

    samples = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pair = row_to_sample(row)
        if pair:
            samples.append(pair)
            count += 1

    return count, samples


def main():
    parser = argparse.ArgumentParser(description="Tai dataset TOEIC tu Hugging Face")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Ghi de finetune_dataset.jsonl",
    )
    args = parser.parse_args()

    try:
        import datasets  # noqa: F401
    except ImportError:
        print("Chay: pip install datasets")
        sys.exit(1)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if args.overwrite else "a"
    total = 0
    seen = set()

    print("Tim dataset tren Hugging Face (neu loi schema, bo qua va thu nguon khac)...\n")

    for repo_id, split in HF_SOURCES:
        try:
            print(f"  [{repo_id}] ...")
            count, samples = load_one_dataset(repo_id, split)
            written = 0
            with open(OUTPUT_FILE, mode, encoding="utf-8") as f:
                for inst, out in samples:
                    key = (inst[:200], out[:200])
                    if key in seen:
                        continue
                    seen.add(key)
                    f.write(json.dumps(to_chat(inst, out), ensure_ascii=False) + "\n")
                    written += 1
                mode = "a"
            total += written
            print(f"       -> {written} mau (parse duoc {count} dong)\n")
        except Exception as e:
            print(f"       [!] Bo qua: {e}\n")

    print(f"Tong cong them ~{total} mau vao: {OUTPUT_FILE}")
    if total == 0:
        print(
            "\nKhong tai duoc nguon nao. Thu:\n"
            "  pip install -U datasets\n"
            "  Hoac vao https://huggingface.co/datasets?search=TOEIC tim repo khac."
        )


if __name__ == "__main__":
    main()
