import asyncio
import json
import os
import sys
from pathlib import Path

# Fix Windows console UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to PYTHONPATH
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from app.services.llm_service import llm_service
from app.core.config import get_settings

JUDGE_PROMPT = """Bạn là một giám khảo chuyên nghiệp đánh giá hệ thống AI gia sư tiếng Anh.
Hãy so sánh Câu trả lời thực tế (Actual Answer) của hệ thống với Câu trả lời chuẩn (Ground Truth).
Chấm điểm từ 1 đến 5 cho từng tiêu chí sau:
1. Accuracy (Tính chính xác): Giải thích có đúng kiến thức không? Có chọn đúng đáp án không?
2. Tone (Giọng văn): Có thân thiện, xưng "Em ơi" và giải thích gần gũi như giáo viên Việt Nam không?
3. Format (Định dạng): Có trình bày rõ ràng, dễ đọc không?

Trả về kết quả DƯỚI DẠNG JSON với cấu trúc:
{
  "accuracy_score": <int>,
  "tone_score": <int>,
  "format_score": <int>,
  "reasoning": "<Giải thích ngắn gọn lý do cho điểm>"
}
CHỈ trả về chuỗi JSON, không có code block.
"""

async def evaluate_single(question: str, ground_truth: str):
    print(f"\n[?] Đang hỏi AI: {question[:50]}...")
    # Lấy câu trả lời thực tế từ hệ thống ViEng
    # Sử dụng llm_provider='auto' để tự động dùng cấu hình mặc định (OpenRouter)
    actual_answer = await llm_service.chat(
        message=f"Giai thich cau hoi TOEIC sau cho hoc sinh Viet Nam:\n{question}\nHay giai thich theo phong cach thay co Viet Nam: than thien, gan gui, dung vi du doi thuong, co meo ghi nho. Bat dau bang 'Em oi' hoac tuong tu.",
        history=[],
        rag_context="", # Giả lập không dùng RAG cho bài test này, hoặc có thể truyền context thật
        llm_provider="auto"
    )
    
    print(f"[*] AI trả lời: {actual_answer[:50]}...")
    
    # Đánh giá bằng LLM as a Judge
    judge_client = llm_service._openrouter_client
    if not judge_client:
        print("Lỗi: Không tìm thấy OpenRouter client để làm giám khảo.")
        return None
        
    judge_message = f"""Câu hỏi: {question}

Ground Truth: {ground_truth}

Actual Answer: {actual_answer}"""

    response = await judge_client.chat.completions.create(
        model="openai/gpt-4o-mini",
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": judge_message}
        ],
        temperature=0.1
    )
    
    result_str = response.choices[0].message.content.strip()
    # Loại bỏ code block nếu AI lỡ sinh ra
    if result_str.startswith("```json"):
        result_str = result_str[7:-3]
    elif result_str.startswith("```"):
        result_str = result_str[3:-3]
        
    try:
        score_data = json.loads(result_str)
        score_data["actual_answer"] = actual_answer
        return score_data
    except Exception as e:
        print(f"Lỗi parse JSON từ giám khảo: {e}\nRaw: {result_str}")
        return None

async def main():
    settings = get_settings()
    if not settings.openrouter_api_key:
        print("Vui lòng cấu hình OPENROUTER_API_KEY trong file .env trước khi chạy eval.")
        return
        
    dataset_path = Path(__file__).parent / "eval_dataset.jsonl"
    if not dataset_path.exists():
        print(f"Không tìm thấy file {dataset_path}")
        return
        
    dataset = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                dataset.append(json.loads(line))
                
    print(f"Bắt đầu đánh giá {len(dataset)} câu hỏi...")
    results = []
    
    for item in dataset:
        score = await evaluate_single(item["question"], item["ground_truth_explanation"])
        if score:
            results.append({
                "question": item["question"],
                "scores": score
            })
            print(f"-> Điểm: Accuracy={score.get('accuracy_score')}, Tone={score.get('tone_score')}, Format={score.get('format_score')}")
            print(f"-> Lý do: {score.get('reasoning')}")
            
    # Tổng kết
    if results:
        avg_acc = sum(r["scores"].get("accuracy_score", 0) for r in results) / len(results)
        avg_tone = sum(r["scores"].get("tone_score", 0) for r in results) / len(results)
        avg_fmt = sum(r["scores"].get("format_score", 0) for r in results) / len(results)
        
        print("\n" + "="*40)
        print("KẾT QUẢ ĐÁNH GIÁ (EVALUATION REPORT)")
        print("="*40)
        print(f"Số lượng mẫu: {len(results)}")
        print(f"Điểm Chính xác (Accuracy): {avg_acc:.2f}/5")
        print(f"Điểm Giọng văn (Tone):    {avg_tone:.2f}/5")
        print(f"Điểm Định dạng (Format):  {avg_fmt:.2f}/5")
        print("="*40)
        
        # Ghi ra file
        report_path = Path(__file__).parent / "eval_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Chi tiết đánh giá đã được lưu tại: {report_path}")

if __name__ == "__main__":
    asyncio.run(main())
