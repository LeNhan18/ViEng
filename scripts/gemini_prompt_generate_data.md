# Prompt dùng với Gemini để sinh dataset fine-tune cho ViEng

## Cách dùng

1. Copy prompt bên dưới vào Gemini
2. Thay `[CHỦ ĐỀ]` và `[TÀI LIỆU]` theo hướng dẫn
3. Copy output của Gemini, paste vào cuối file `data/finetune_dataset.jsonl` (mỗi mẫu 1 dòng)
4. Lặp lại với các chủ đề khác

---

## PROMPT 1: Sinh câu hỏi TOEIC Part 5 + Giải thích (có RAG context)

```
Bạn đang giúp tôi tạo dataset fine-tune cho LLM luyện thi TOEIC. Hãy sinh DỮ LIỆU TRAINING theo format JSONL.

Chủ đề ngữ pháp: [CHỦ ĐỀ]

Tài liệu tham khảo (đóng vai RAG context):
---
[DÁN NỘI DUNG TỪ FILE KNOWLEDGE BASE VÀO ĐÂY]
---

Hãy sinh ĐÚNG 3 cặp mẫu (6 dòng JSONL tổng cộng). Mỗi cặp gồm:

**Mẫu A - Sinh câu hỏi:**
{"conversations": [{"role": "system", "content": "Ban la giao vien luyen thi TOEIC chuyen nghiep tai Viet Nam. Khi duoc cung cap tai lieu tham khao, hay su dung noi dung do de tao cau hoi chinh xac hon. Luon tra ve JSON hop le."}, {"role": "user", "content": "Dua vao tai lieu duoi day (co the bo sung kien thuc ben ngoai neu can).\n\n\n--- Tai lieu (nguon: [TEN_FILE].txt) ---\n[TRICH DOAN TAI LIEU]\n--- Het tai lieu ---\n\nTao 2 cau hoi TOEIC Part 5 (Incomplete Sentences) dua tren quy tac/vi du trong tai lieu. Moi cau 1 cho trong, 4 dap an A/B/C/D. Tra ve JSON array: [{\"id\": 1, \"content\": \"...\", \"options\": [\"A. ...\", \"B. ...\", \"C. ...\", \"D. ...\"], \"correct_answer\": \"B\"}, ...]. Chi tra ve JSON."}, {"role": "assistant", "content": "[JSON ARRAY 2 CÂU HỎI TOEIC PART 5]"}]}

**Mẫu B - Giải thích đáp án (cho MỖI câu hỏi trong mẫu A):**
{"conversations": [{"role": "system", "content": "Ban la thay giao tieng Anh Viet Nam, giai thich than thien, gan gui, de hieu. Khi duoc cung cap tai lieu tham khao, hay dua vao do de giai thich chinh xac hon."}, {"role": "user", "content": "Giai thich cau hoi TOEIC sau cho hoc sinh Viet Nam, dua vao tai lieu tham khao:\n\n\n--- Tai lieu (nguon: [TEN_FILE].txt) ---\n[TRICH DOAN TAI LIEU]\n--- Het tai lieu ---\n\nCau hoi: [NỘI DUNG CÂU HỎI]\nDap an: [4 ĐÁP ÁN]\nDap an dung: [ĐÁP ÁN ĐÚNG]\nHay giai thich theo phong cach thay co Viet Nam: than thien, gan gui, dung vi du doi thuong, co meo ghi nho. Bat dau bang 'Em oi' hoac tuong tu."}, {"role": "assistant", "content": "[GIẢI THÍCH CHI TIẾT BẰNG TIẾNG VIỆT, bắt đầu bằng 'Em oi', giọng thầy cô Việt Nam, có mẹo ghi nhớ, ví dụ đời thường, 150-300 từ]"}]}

YÊU CẦU QUAN TRỌNG:
1. Mỗi dòng là 1 JSON object hoàn chỉnh (JSONL format)
2. KHÔNG xuống dòng trong JSON, mỗi mẫu nằm trọn trên 1 dòng
3. Câu hỏi TOEIC Part 5 phải đúng format: 1 câu tiếng Anh có chỗ trống (______), 4 đáp án A/B/C/D, chủ đề business/office
4. Giải thích phải bằng tiếng Việt, thân thiện, bắt đầu "Em oi"
5. RAG context trong user message phải trích từ tài liệu tham khảo ở trên
6. Câu hỏi phải DỰA TRÊN quy tắc trong tài liệu tham khảo
7. Escape đúng JSON: dùng \" cho dấu ngoặc kép, \n cho xuống dòng

Hãy sinh 3 cặp (6 dòng JSONL) ngay bây giờ:
```

---

## PROMPT 2: Sinh thêm dạng Part 6 (Text Completion)

```
Bạn đang giúp tôi tạo dataset fine-tune cho LLM luyện thi TOEIC.

Chủ đề: [CHỦ ĐỀ - ví dụ: connectors, transitions, conjunctions]

Tài liệu tham khảo:
---
[DÁN NỘI DUNG TỪ FILE KNOWLEDGE BASE]
---

Sinh 2 mẫu JSONL cho TOEIC Part 6 (Text Completion). Format:

{"conversations": [{"role": "system", "content": "Ban la giao vien luyen thi TOEIC chuyen nghiep tai Viet Nam. Khi duoc cung cap tai lieu tham khao, hay su dung noi dung do de tao cau hoi chinh xac hon. Luon tra ve JSON hop le."}, {"role": "user", "content": "Dua vao tai lieu duoi day.\n\n--- Tai lieu (nguon: [TEN_FILE].txt) ---\n[TRICH DOAN]\n--- Het tai lieu ---\n\nTao 1 doan van TOEIC Part 6 (Text Completion): 1 email/memo 100-150 tu, co 4 cho trong (1)(2)(3)(4), moi cho 4 dap an A/B/C/D. Tra ve JSON array: [{\"passage\": \"...\", \"questions\": [{\"id\": 1, \"content\": \"(1)\", \"options\": [...], \"correct_answer\": \"A\"}, ...]}]. Chi tra ve JSON."}, {"role": "assistant", "content": "[JSON ARRAY]"}]}

YÊU CẦU:
- Mỗi dòng 1 JSON hoàn chỉnh, KHÔNG xuống dòng
- Đoạn văn Part 6 phải là email/memo/thông báo business
- 4 chỗ trống kiểm tra: connector, word form, grammar, vocabulary
- Escape JSON đúng cách

Sinh 2 mẫu JSONL ngay:
```

---

## PROMPT 3: Sinh giải thích cho câu hỏi có sẵn

Nếu bạn đã có câu hỏi TOEIC và chỉ muốn sinh thêm phần giải thích:

```
Sinh mẫu training JSONL cho giải thích đáp án TOEIC.

Câu hỏi: [PASTE CÂU HỎI]
Đáp án: [A. ..., B. ..., C. ..., D. ...]
Đáp án đúng: [X]
Chủ đề ngữ pháp: [CHỦ ĐỀ]

Tài liệu tham khảo:
---
[DÁN NỘI DUNG TỪ FILE KNOWLEDGE BASE]
---

Sinh 1 dòng JSONL theo format:
{"conversations": [{"role": "system", "content": "Ban la thay giao tieng Anh Viet Nam, giai thich than thien, gan gui, de hieu. Khi duoc cung cap tai lieu tham khao, hay dua vao do de giai thich chinh xac hon."}, {"role": "user", "content": "Giai thich cau hoi TOEIC sau cho hoc sinh Viet Nam, dua vao tai lieu tham khao:\n\n--- Tai lieu (nguon: [FILE].txt) ---\n[TRICH DOAN]\n--- Het tai lieu ---\n\nCau hoi: ...\nDap an: ...\nDap an dung: ...\nHay giai thich theo phong cach thay co Viet Nam: than thien, gan gui, dung vi du doi thuong, co meo ghi nho. Bat dau bang 'Em oi' hoac tuong tu."}, {"role": "assistant", "content": "[GIẢI THÍCH 150-300 từ tiếng Việt, bắt đầu Em oi]"}]}

YÊU CẦU:
- 1 dòng JSON duy nhất, không xuống dòng
- Giải thích: (1) tại sao đáp án đúng, (2) tại sao các đáp án khác sai, (3) mẹo ghi nhớ
- Giọng văn thầy cô Việt Nam thân thiện
- Trích dẫn quy tắc từ tài liệu tham khảo

Sinh ngay:
```

---

## Danh sách chủ đề gợi ý để sinh data

Thay `[CHỦ ĐỀ]` bằng các topic dưới đây, kết hợp với nội dung file tương ứng:

| Chủ đề | File knowledge base |
|--------|-------------------|
| Present Simple vs Present Continuous | 01_tenses.txt |
| Present Perfect vs Past Simple | 01_tenses.txt |
| Word forms (noun/adj/adv/verb) | 03_word_forms.txt |
| Parts of speech | 03_parts_of_speech.txt |
| Common TOEIC mistakes | 03_toeic_common_mistakes.txt |
| Conditionals (Type 1/2/3) | 04_conditionals.txt |
| Prepositions (time/place) | 04_prepositions.txt, 20_prepositions_time_place.txt |
| Conjunctions & Connectors | 05_conjunctions_connectors.txt |
| Connectors & Transitions (Part 6) | 06_connectors_transitions.txt |
| Relative clauses | 06_relative_clauses.txt |
| Passive voice | 08_passive_voice.txt, 10_passive_voice.txt |
| Gerund vs Infinitive | 10_gerund_infinitive.txt, 19_gerund_infinitive.txt |
| Subject-verb agreement | 11_subject_verb_agreement.txt |
| Articles (a/an/the) | 12_articles.txt, 13_articles.txt |
| Reported speech | 11_reported_speech.txt |
| Comparisons | 12_comparisons.txt |
| Phrasal verbs | 14_phrasal_verbs_toeic.txt |
| Collocations | 15_collocations_toeic.txt |
| TOEIC vocabulary | 07_vocabulary_toeic.txt, 11_toeic_vocabulary.txt |

## Sau khi có output từ Gemini

1. Copy output (các dòng JSONL)
2. Mở file `data/finetune_dataset.jsonl`
3. Paste vào cuối file (mỗi mẫu 1 dòng)
4. Kiểm tra JSON hợp lệ: mỗi dòng phải parse được bằng `json.loads()`
