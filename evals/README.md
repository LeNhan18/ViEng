# ViEng eval

Đo chất lượng AI bằng LLM thật, chặn PR khi chất lượng tụt dưới ngưỡng (`thresholds.json`).

| Suite | Làm gì | Chỉ số (ngưỡng) |
|---|---|---|
| `solver_baseline` | Solver làm 30 câu Part 5 chuẩn (`datasets/part5_golden.jsonl`) | `accuracy` ≥ 0.9 |
| `generation` | Sinh đề Part 5/6/7 thật, rồi cho solver (model thứ hai) làm thử | `generation_success_rate` ≥ 0.95, `repair_rate` ≤ 0.5, `solver_agreement` ≥ 0.85 |
| `explain` | Giải thích cho học sinh chọn sai, judge chấm | `pass_rate` ≥ 0.85 |
| `chat` | Chatbot trả lời 15 câu ngữ pháp (`datasets/chat_golden.jsonl`), judge chấm | `key_point_coverage` ≥ 0.8, `answers_with_errors_rate` ≤ 0.1 |

`solver_baseline` cho biết solver có đáng tin không. Nếu solver yếu, `solver_agreement` thấp có thể do solver chứ không phải do đề.
Câu solver chọn khác đáp án đề được liệt kê trong report (`failures`, `kind: solver_disagrees`) để người duyệt lại.

## Chạy

```bash
pip install -r requirements.lite.txt -r requirements-dev.txt
export OPENROUTER_API_KEY=...
# Tuỳ chọn, nên khác họ với LLM_MODEL để giảm thiên vị tự chấm:
export EVAL_SOLVER_MODEL=... EVAL_JUDGE_MODEL=...

python -m evals.run --quick                 # ~1-2 phút, dùng cho PR
python -m evals.run                         # đầy đủ
python -m evals.run --suite generation,chat # chọn suite
```

Report: `evals/reports/latest.json`. Exit code 1 nếu có chỉ số dưới ngưỡng.

## CI

- `ci.yml`: cài đúng deps của Docker image (lite), chạy `pytest` (gồm test cho chính bộ eval với LLM giả, không cần key).
- `eval.yml`: chạy eval thật khi PR sửa `app/services/**` hoặc `evals/**` (quick), thủ công (`workflow_dispatch`), và mỗi thứ Hai (full). Cần secret `OPENROUTER_API_KEY`; thiếu key thì tự bỏ qua.

## Thêm dữ liệu

- Câu Part 5: thêm dòng vào `part5_golden.jsonl`. Test `tests/test_evals.py` kiểm tra định dạng và phân bố đáp án A–D.
- Câu chat: thêm `question` + `key_points` (các ý bắt buộc phải có) vào `chat_golden.jsonl`.
