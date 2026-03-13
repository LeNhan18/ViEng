"""
Script tải và chuyển đổi datasets từ HuggingFace vào knowledge base.

Cách chạy:
    pip install datasets
    python scripts/download_datasets.py
"""

from datasets import load_dataset
from pathlib import Path


OUTPUT_DIR = Path("data/knowledge_base")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_ielts_writing():
    """Tải IELTS Writing Task 2 dataset và chuyển thành .txt cho RAG."""
    print("Đang tải IELTS Writing Task 2 dataset...")
    ds = load_dataset("chillies/IELTS-writing-task-2-evaluation")

    train = ds["train"]
    print(f"Số lượng bài essay: {len(train)}")

    band_groups = {}
    for row in train:
        band = str(row.get("band_score", row.get("score", "unknown")))
        if band not in band_groups:
            band_groups[band] = []
        band_groups[band].append(row)

    output_file = OUTPUT_DIR / "07_ielts_writing_samples.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# IELTS Writing Task 2 - Bài mẫu và đánh giá\n\n")

        for band in sorted(band_groups.keys(), reverse=True):
            essays = band_groups[band]
            samples = essays[:5]

            f.write(f"## Band {band} ({len(essays)} bài trong dataset)\n\n")

            for i, row in enumerate(samples, 1):
                prompt = row.get("prompt", row.get("question", "N/A"))
                essay = row.get("essay", row.get("response", "N/A"))
                evaluation = row.get("evaluation", row.get("feedback", ""))

                f.write(f"### Bài mẫu {i}\n")
                f.write(f"- Đề bài: {prompt}\n")
                f.write(f"- Band Score: {band}\n")

                essay_preview = essay[:500] + "..." if len(str(essay)) > 500 else essay
                f.write(f"- Bài viết (trích):\n{essay_preview}\n")

                if evaluation:
                    eval_preview = str(evaluation)[:300] + "..." if len(str(evaluation)) > 300 else evaluation
                    f.write(f"- Nhận xét: {eval_preview}\n")

                f.write("\n")

    print(f"Đã lưu vào {output_file}")

    tips_file = OUTPUT_DIR / "08_ielts_writing_tips.txt"
    with open(tips_file, "w", encoding="utf-8") as f:
        f.write("""# IELTS Writing Task 2 - Hướng dẫn viết essay

## Cấu trúc bài essay chuẩn (4 đoạn)

### Đoạn 1: Introduction (2-3 câu)
- Câu 1: Paraphrase lại đề bài (KHÔNG copy nguyên văn)
- Câu 2-3: Nêu thesis statement (quan điểm của bạn)
- Ví dụ: "It is often argued that... In my opinion, I believe that..."

### Đoạn 2: Body Paragraph 1 (5-7 câu)
- Topic sentence: Nêu ý chính
- Explanation: Giải thích
- Example: Ví dụ cụ thể
- Link: Liên kết lại với thesis

### Đoạn 3: Body Paragraph 2 (5-7 câu)
- Tương tự đoạn 2, với ý chính thứ 2
- Nếu đề yêu cầu "discuss both views": đoạn này nêu quan điểm đối lập

### Đoạn 4: Conclusion (2-3 câu)
- Tóm tắt lại quan điểm (paraphrase thesis)
- KHÔNG đưa thêm ý mới

## Tiêu chí chấm điểm (Band Descriptors)

### Task Response (25%)
- Trả lời đúng và đầy đủ tất cả phần của đề
- Có thesis statement rõ ràng
- Develop ideas đầy đủ với examples

### Coherence & Cohesion (25%)
- Ý tưởng được sắp xếp logic
- Dùng linking words phù hợp (However, Furthermore, In addition)
- Mỗi đoạn có topic sentence rõ ràng

### Lexical Resource (25%)
- Dùng từ vựng đa dạng, chính xác
- Paraphrase thay vì lặp từ
- Collocations tự nhiên

### Grammatical Range & Accuracy (25%)
- Dùng đa dạng cấu trúc câu (simple, compound, complex)
- Ít lỗi ngữ pháp
- Dùng đúng thì, articles, prepositions

## Các dạng đề phổ biến

### Opinion (Agree/Disagree)
- "To what extent do you agree or disagree?"
- Cần nêu rõ quan điểm từ Introduction

### Discussion (Discuss both views)
- "Discuss both views and give your own opinion."
- Body 1: View A | Body 2: View B | Conclusion: Your opinion

### Problem-Solution
- "What are the problems? What solutions can you suggest?"
- Body 1: Problems | Body 2: Solutions

### Advantages-Disadvantages
- "Do the advantages outweigh the disadvantages?"
- Body 1: Advantages | Body 2: Disadvantages | Conclusion: đánh giá

## Từ vựng Academic hay dùng

### Nêu quan điểm
- I firmly believe that... / In my opinion... / From my perspective...
- It is widely acknowledged that... / There is a growing consensus that...

### Thêm ý
- Furthermore, Moreover, In addition, Additionally, What is more

### Tương phản
- However, Nevertheless, On the other hand, Conversely, In contrast

### Ví dụ
- For example, For instance, To illustrate, A case in point is...

### Kết luận
- In conclusion, To sum up, All things considered, Taking everything into account
""")

    print(f"Đã lưu IELTS writing tips vào {tips_file}")


def download_grammar_correction():
    """Tải Grammar Correction dataset."""
    print("\nĐang tải Grammar Correction dataset...")
    ds = load_dataset("agentlans/grammar-correction", split="train[:1000]")

    output_file = OUTPUT_DIR / "09_grammar_correction_examples.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Grammar Correction Examples - Ví dụ sửa lỗi ngữ pháp\n\n")
        f.write("Mỗi cặp gồm câu SAI và câu ĐÚNG, giúp nhận diện lỗi phổ biến.\n\n")

        for i, row in enumerate(ds):
            incorrect = row.get("input", row.get("incorrect", ""))
            correct = row.get("output", row.get("correct", ""))
            if incorrect and correct and incorrect != correct:
                f.write(f"- Sai: {incorrect}\n")
                f.write(f"  Đúng: {correct}\n\n")

            if i >= 499:
                break

    print(f"Đã lưu 500 ví dụ vào {output_file}")


if __name__ == "__main__":
    print("=" * 50)
    print("ViEng - Download Datasets cho Knowledge Base")
    print("=" * 50)

    download_ielts_writing()
    download_grammar_correction()

    print("\n✓ Hoàn tất! Các file đã được lưu vào data/knowledge_base/")
    print("Bước tiếp: Chạy API và gọi POST /api/v1/rag/index để index vào ChromaDB")
