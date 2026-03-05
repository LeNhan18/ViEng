# ViEng
## Chi Tiết Dự Án
1. Mục Tiêu Tổng Thể

Xây dựng một ứng dụng web/mobile hỗ trợ sinh viên Việt Nam luyện thi TOEIC/IELTS một cách cá nhân hóa, sử dụng AI để tạo bài tập, phân tích lỗi sai, và cung cấp feedback tức thì.
Kết hợp công nghệ chính:
Fine-tuning LLM: Tinh chỉnh mô hình để "học" phong cách giải thích kiểu thầy cô Việt (thân thiện, gần gũi, dùng ví dụ đời thường), tạo bài test dựa trên level người dùng, và xử lý tiếng Việt tự nhiên.
RAG: Tích hợp để truy xuất thông tin động từ nguồn uy tín (grammar rules, từ vựng, bài mẫu), đảm bảo câu trả lời chính xác, cập nhật (ví dụ: thay đổi format thi mới nhất từ ETS), và giảm hallucination (mô hình không bịa thông tin).

Đối tượng người dùng: Sinh viên đại học (như ĐH Bách Khoa, Kinh Tế TP.HCM), người đi làm cần chứng chỉ tiếng Anh. Ước tính impact: Giúp 100-500 users beta test, cải thiện điểm thi 10-20% qua feedback cá nhân hóa.
Lợi ích kinh doanh/thực tế: Miễn phí cơ bản, premium cho voice mode; có thể mở rộng thành startup hoặc contribute open-source để tăng visibility trên GitHub.

2. Tính Năng Chính

Tạo bài test cá nhân hóa: User chọn kỹ năng (Listening, Reading, Speaking, Writing) và level (Beginner/Intermediate/Advanced). LLM generate questions dựa trên dataset fine-tune.
Phân tích và giải thích lỗi: Sau khi user trả lời, mô hình kiểm tra và explain kiểu "Thầy cô Việt" (ví dụ: "Em sai ở phần này vì nhầm thì hiện tại hoàn thành với quá khứ đơn. Thầy ví dụ: 'I have eaten' nghĩa là...").
RAG integration: Khi explain, pull từ knowledge base (grammar/from vựng từ British Council/IDP) để trích dẫn nguồn chính xác.
Voice mode (optional nâng cao): Sử dụng Whisper để user luyện speaking/listening; LLM evaluate pronunciation, fluency, và gợi ý cải thiện.
Tiến độ tracking: Dashboard theo dõi progress (điểm số, điểm yếu), gợi ý bài tập tiếp theo.
An toàn & đạo đức: Không lưu dữ liệu cá nhân mà không có consent; sử dụng watermarking để tránh misuse.

3. Architecture Tổng Thể

Backend: Python với FastAPI/Flask cho API.
LLM: Base model như Llama-3-8B hoặc Vietcuna-7B (fine-tune với LoRA để tiết kiệm GPU).
RAG Pipeline: LangChain/LlamaIndex để build chain: Embed query → Retrieve từ vector DB (Chroma/FAISS) → Augment prompt cho LLM.
Knowledge Base: Vector store chứa chunks từ crawl/scrape nguồn (British Council, Cambridge, ETS samples).

Frontend: Streamlit/Gradio cho prototype web; nếu mobile, dùng React Native + API.
Deployment: Heroku/Vercel miễn phí cho demo; AWS/GCP nếu scale.
Data Flow Example:
User hỏi: "Tạo bài test TOEIC Part 7 level B2."
Fine-tuned LLM generate questions.
User trả lời → RAG retrieve rules liên quan → LLM explain với style Việt.
