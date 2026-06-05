import { useState, useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { generateTest } from "../api";
import { Loader2, ChevronRight, ChevronLeft, CheckCircle2, BookOpen, Sparkles, Bookmark, Flag } from "lucide-react";
import LlmProviderSelect from "../components/LlmProviderSelect";

const EXAM_TYPES = [
  { value: "toeic", label: "TOEIC", desc: "Chứng chỉ tiếng Anh giao tiếp nghề nghiệp", color: "border-blue-500 bg-blue-50/50 text-blue-700 hover:border-blue-600 shadow-blue-500/5" },
  { value: "ielts", label: "IELTS", desc: "Hệ thống kiểm tra Anh ngữ quốc tế", color: "border-emerald-500 bg-emerald-50/50 text-emerald-700 hover:border-emerald-600 shadow-emerald-500/5" },
];

const TOEIC_READING_PARTS = [
  {
    value: "part5",
    label: "Part 5",
    desc: "Incomplete Sentences",
    detail: "Hoàn thành câu - 30 câu chuẩn đề thi",
    defaultN: 10,
    maxN: 30,
  },
  {
    value: "part6",
    label: "Part 6",
    desc: "Text Completion",
    detail: "Hoàn thành đoạn văn - 4 đoạn x 4 câu",
    defaultN: 8,
    maxN: 16,
  },
  {
    value: "part7_single",
    label: "Part 7 (Single)",
    desc: "Single Passage",
    detail: "Đọc hiểu một văn bản đơn - 2-4 câu/bài",
    defaultN: 6,
    maxN: 29,
  },
  {
    value: "part7_multiple",
    label: "Part 7 (Multi)",
    desc: "Multiple Passages",
    detail: "Đọc hiểu nhiều văn bản liên kết - 5 câu/bộ",
    defaultN: 5,
    maxN: 25,
  },
];

const LEVELS = [
  { value: "beginner", label: "Beginner", desc: "Mới bắt đầu ôn luyện" },
  { value: "intermediate", label: "Intermediate", desc: "Trình độ trung cấp (Mục tiêu 550-650 TOEIC)" },
  { value: "advanced", label: "Advanced", desc: "Trình độ nâng cao (Mục tiêu 750+ hoặc IELTS 6.5+)" },
];

export default function Exam() {
  const navigate = useNavigate();
  const location = useLocation();

  const [step, setStep] = useState("setup");
  const [config, setConfig] = useState({
    examType: "toeic",
    skill: "reading",
    level: "intermediate",
    part: "part5",
    numQuestions: 10,
    llmProvider: localStorage.getItem("vieng_llm_provider") || "groq",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [testData, setTestData] = useState(null);
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState({});
  const [flagged, setFlagged] = useState({}); // Stores flagged questions: { [questionId]: boolean }

  const selectedPartInfo = TOEIC_READING_PARTS.find((p) => p.value === config.part);

  // Read forwarded state (from Home tag clicks)
  useEffect(() => {
    if (location.state) {
      setConfig((c) => ({
        ...c,
        ...location.state,
      }));
      // Clear location state
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  function handlePartChange(partValue) {
    const part = TOEIC_READING_PARTS.find((p) => p.value === partValue);
    setConfig((c) => ({
      ...c,
      part: partValue,
      numQuestions: part?.defaultN || 5,
    }));
  }

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      localStorage.setItem("vieng_llm_provider", config.llmProvider);
      const data = await generateTest(config);
      setTestData(data);
      setAnswers({});
      setFlagged({});
      setCurrent(0);
      setStep("quiz");
    } catch (err) {
      setError(err.response?.data?.detail || "Không thể tạo đề thi. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  function handleSelect(questionId, answer) {
    setAnswers((prev) => ({ ...prev, [questionId]: answer }));
  }

  function toggleFlag(questionId) {
    setFlagged((prev) => ({ ...prev, [questionId]: !prev[questionId] }));
  }

  function handleSubmit() {
    const questions = testData?.questions || [];
    const resultData = {
      config,
      questions,
      answers,
      readingSection: testData?.reading_section,
      score: questions.reduce((acc, q) => {
        const selected = answers[q.id];
        const correct = q.correct_answer;
        const isCorrect = selected && (selected === correct || selected.startsWith(correct));
        return acc + (isCorrect ? 1 : 0);
      }, 0),
    };
    navigate("/result", { state: resultData });
  }

  if (step === "setup") {
    return (
      <div className="mx-auto max-w-3xl space-y-8 py-4">
        {/* Header */}
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
            <Sparkles size={12} className="text-indigo-600 animate-pulse" />
            <span>Đề thi độc quyền biên soạn bằng Trí tuệ nhân tạo</span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 md:text-4xl">Tạo Đề Thi Cá Nhân Hóa</h1>
          <p className="text-slate-500 max-w-md mx-auto text-sm md:text-base">
            Cấu hình nhanh dạng bài thi và độ khó, AI sẽ chuẩn bị bộ đề thi phù hợp ngay lập tức.
          </p>
        </div>

        {/* Setup Configuration Form */}
        <div className="space-y-6 rounded-3xl border border-slate-200/80 bg-white p-6 md:p-8 shadow-xl shadow-slate-100">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <label className="text-sm font-bold text-slate-700">Chọn model tạo đề</label>
            <LlmProviderSelect
              value={config.llmProvider}
              onChange={(v) => setConfig((c) => ({ ...c, llmProvider: v }))}
            />
          </div>

          {/* Exam type */}
          <div className="space-y-3">
            <label className="block text-sm font-bold text-slate-700">Kỳ thi mục tiêu</label>
            <div className="grid gap-3 sm:grid-cols-2">
              {EXAM_TYPES.map(({ value, label, desc, color }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setConfig((c) => ({ ...c, examType: value }))}
                  className={`rounded-2xl border-2 p-4 text-left transition-all cursor-pointer ${
                    config.examType === value
                      ? `${color} ring-4 ring-indigo-500/10`
                      : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"
                  }`}
                >
                  <div className={`text-base font-extrabold ${config.examType === value ? "text-indigo-900" : "text-slate-800"}`}>
                    {label}
                  </div>
                  <div className="text-xs text-slate-400 mt-1 font-semibold">{desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Parts (TOEIC only) */}
          {config.examType === "toeic" && (
            <div className="space-y-3">
              <label className="block text-sm font-bold text-slate-700">Dạng bài TOEIC Reading</label>
              <div className="grid gap-3 sm:grid-cols-2">
                {TOEIC_READING_PARTS.map(({ value, label, desc, detail }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => handlePartChange(value)}
                    className={`rounded-2xl border-2 p-4 text-left transition-all cursor-pointer ${
                      config.part === value
                        ? "border-indigo-600 bg-indigo-50/50 ring-4 ring-indigo-500/10"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-sm font-extrabold ${config.part === value ? "text-indigo-900" : "text-slate-800"}`}>
                        {label}
                      </span>
                      <span className="text-[10px] bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-bold">
                        {desc}
                      </span>
                    </div>
                    <div className="mt-2 text-xs font-semibold text-slate-500">{detail}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Levels */}
          <div className="space-y-3">
            <label className="block text-sm font-bold text-slate-700">Trình độ của bạn</label>
            <div className="grid gap-3 sm:grid-cols-3">
              {LEVELS.map(({ value, label, desc }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setConfig((c) => ({ ...c, level: value }))}
                  className={`rounded-2xl border-2 p-4 text-left transition-all cursor-pointer ${
                    config.level === value
                      ? "border-indigo-600 bg-indigo-50/50 ring-4 ring-indigo-500/10"
                      : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <div className={`text-sm font-extrabold ${config.level === value ? "text-indigo-900" : "text-slate-800"}`}>
                    {label}
                  </div>
                  <div className="text-xs text-slate-400 mt-1.5 font-semibold">{desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Question count */}
          <div className="space-y-3">
            <div className="flex justify-between items-center text-sm font-bold text-slate-700">
              <span>Số câu hỏi mong muốn</span>
              <span className="text-indigo-600 text-base font-extrabold">{config.numQuestions} câu</span>
            </div>
            <div className="bg-slate-50 p-4 rounded-2xl border border-slate-100">
              <input
                type="range"
                min={2}
                max={selectedPartInfo?.maxN || 30}
                value={config.numQuestions}
                onChange={(e) => setConfig((c) => ({ ...c, numQuestions: +e.target.value }))}
                className="w-full accent-indigo-600 h-2 bg-slate-200 rounded-lg cursor-pointer"
              />
              <div className="flex justify-between text-xs text-slate-400 mt-2 font-bold">
                <span>2 câu</span>
                <span>{selectedPartInfo?.maxN || 30} câu (Tối đa)</span>
              </div>
            </div>
          </div>

          {error && (
            <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700 animate-fade-in-up">
              ⚠️ {error}
            </div>
          )}

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-2xl bg-indigo-600 hover:bg-indigo-500 px-6 py-4 text-base font-extrabold text-white shadow-xl shadow-indigo-600/30 transition-all hover:scale-[1.01] active:scale-95 disabled:cursor-not-allowed disabled:opacity-60 cursor-pointer"
          >
            {loading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                AI đang biên soạn và tối ưu đề thi...
              </>
            ) : (
              <>
                <BookOpen size={18} />
                Bắt đầu biên soạn đề thi
              </>
            )}
          </button>
        </div>
      </div>
    );
  }

  const questions = testData?.questions || [];
  const section = testData?.reading_section;
  const part = testData?.part;
  const q = questions[current];
  const totalAnswered = Object.keys(answers).length;
  const completionPercentage = questions.length ? Math.round((totalAnswered / questions.length) * 100) : 0;

  const partLabel =
    part === "part5" ? "Part 5 - Incomplete Sentences" :
    part === "part6" ? "Part 6 - Text Completion" :
    part === "part7_single" ? "Part 7 - Single Passage" :
    part === "part7_multiple" ? "Part 7 - Multiple Passages" :
    `${config.examType.toUpperCase()} Reading`;

  function findPassageForQuestion(questionId) {
    if (!section) return null;

    if (part === "part6" && section.part6) {
      for (const p of section.part6) {
        if (p.questions.some((pq) => pq.id === questionId)) {
          return { type: "part6", passage: p.passage };
        }
      }
    }

    const part7list = part === "part7_single" ? section.part7_single : section.part7_multiple;
    if (part7list) {
      for (const p of part7list) {
        if (p.questions.some((pq) => pq.id === questionId)) {
          return { type: part, passages: p.passages };
        }
      }
    }

    return null;
  }

  const passageInfo = q ? findPassageForQuestion(q.id) : null;

  return (
    <div className="mx-auto max-w-6xl space-y-6 py-2">
      {/* Test taking progress header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/60 pb-4">
        <div>
          <h2 className="text-xl font-extrabold text-slate-900">{partLabel}</h2>
          <div className="flex gap-2.5 text-xs text-slate-500 font-semibold mt-1">
            <span>Trình độ: <span className="text-indigo-600 uppercase font-extrabold">{config.level}</span></span>
            <span>•</span>
            <span>Mô hình: <span className="text-indigo-600 font-extrabold uppercase">{config.llmProvider}</span></span>
          </div>
        </div>
        
        {/* Progress Bar Container */}
        <div className="flex items-center gap-4 min-w-[260px]">
          <div className="flex-1">
            <div className="flex justify-between text-[11px] font-bold text-slate-500 mb-1">
              <span>Tiến độ làm bài</span>
              <span>{totalAnswered}/{questions.length} câu</span>
            </div>
            <div className="h-2 w-full bg-slate-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-indigo-600 rounded-full transition-all duration-300 shadow-sm"
                style={{ width: `${completionPercentage}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Workspace split */}
      <div className="grid md:grid-cols-3 gap-6 items-start">
        {/* Left 2 cols: Passage and Question */}
        <div className="md:col-span-2 space-y-6">
          {/* Passage Area */}
          {passageInfo && (
            <div className="rounded-3xl border border-slate-200 bg-slate-50/70 p-5 space-y-4 shadow-sm">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-200/50">
                <span className="h-2.5 w-2.5 rounded-full bg-indigo-500" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Đọc hiểu đoạn văn bên dưới</h3>
              </div>
              
              {passageInfo.type === "part6" && (
                <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700 font-medium bg-white p-4 rounded-2xl border border-slate-100 shadow-sm">
                  {passageInfo.passage}
                </div>
              )}
              
              {(passageInfo.type === "part7_single" || passageInfo.type === "part7_multiple") && (
                <div className="space-y-4">
                  {passageInfo.passages.map((text, idx) => (
                    <div key={idx} className="space-y-1.5">
                      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Văn bản {idx + 1}</div>
                      <div className="whitespace-pre-wrap rounded-2xl bg-white p-4.5 text-sm leading-relaxed text-slate-700 font-medium border border-slate-100 shadow-sm">
                        {text}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Current Question panel */}
          {q && (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-6">
              <div className="flex items-center justify-between">
                <span className="text-xs font-extrabold text-indigo-600 bg-indigo-50 px-3 py-1.5 rounded-full">
                  Câu hỏi {current + 1} trên {questions.length}
                </span>
                
                {/* Flag Question button */}
                <button
                  onClick={() => toggleFlag(q.id)}
                  className={`inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 rounded-xl transition-all cursor-pointer border ${
                    flagged[q.id]
                      ? "bg-amber-50 border-amber-200 text-amber-700"
                      : "bg-white border-slate-200 text-slate-400 hover:text-slate-600 hover:border-slate-300"
                  }`}
                >
                  <Flag size={13} className={flagged[q.id] ? "fill-amber-600" : ""} />
                  <span>{flagged[q.id] ? "Đã đánh dấu" : "Xem lại sau"}</span>
                </button>
              </div>

              <p className="text-base md:text-lg font-bold leading-relaxed text-slate-800">
                {q.content}
              </p>

              {q.options && (
                <div className="space-y-3">
                  {q.options.map((opt) => {
                    const isSelected = answers[q.id] === opt;
                    return (
                      <button
                        key={opt}
                        onClick={() => handleSelect(q.id, opt)}
                        className={`flex w-full items-center gap-3 rounded-2xl border-2 px-5 py-4 text-left transition-all duration-200 cursor-pointer ${
                          isSelected
                            ? "border-indigo-600 bg-indigo-50/70 text-indigo-900 shadow-sm ring-4 ring-indigo-500/5 font-extrabold scale-[1.01]"
                            : "border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50/50"
                        }`}
                      >
                        <div className={`h-5 w-5 rounded-full border flex items-center justify-center text-xs shrink-0 transition-all ${
                          isSelected 
                            ? "bg-indigo-600 border-indigo-600 text-white" 
                            : "border-slate-300 text-slate-400"
                        }`}>
                          {isSelected && "✓"}
                        </div>
                        <span className="text-sm font-semibold">{opt}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Navigation Controls bottom */}
          <div className="flex items-center justify-between">
            <button
              onClick={() => setCurrent((c) => Math.max(0, c - 1))}
              disabled={current === 0}
              className="flex items-center gap-1.5 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-600 transition-all hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            >
              <ChevronLeft size={16} /> Câu trước
            </button>

            {current < questions.length - 1 ? (
              <button
                onClick={() => setCurrent((c) => Math.min(questions.length - 1, c + 1))}
                className="flex items-center gap-1.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 px-5 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-600/15 transition-all hover:scale-[1.02] active:scale-95 cursor-pointer"
              >
                Câu tiếp theo <ChevronRight size={16} />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={totalAnswered < questions.length}
                className="flex items-center gap-1.5 rounded-2xl bg-emerald-600 hover:bg-emerald-500 px-6 py-3 text-sm font-extrabold text-white shadow-lg shadow-emerald-600/15 transition-all hover:scale-[1.02] active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
              >
                <CheckCircle2 size={16} /> Nộp bài ({totalAnswered}/{questions.length})
              </button>
            )}
          </div>
        </div>

        {/* Right 1 col: Question selection grid panel */}
        <div className="rounded-3xl border border-slate-200 bg-white p-5 space-y-5 shadow-sm sticky top-24">
          <div className="pb-3 border-b border-slate-100 space-y-1">
            <h3 className="text-sm font-extrabold text-slate-800">Danh sách câu hỏi</h3>
            <p className="text-[11px] text-slate-400 font-semibold">Chọn số để nhảy nhanh sang câu hỏi khác.</p>
          </div>

          <div className="grid grid-cols-5 gap-2">
            {questions.map((_, i) => {
              const qId = questions[i].id;
              const isCurrent = i === current;
              const isAnswered = !!answers[qId];
              const isFlagged = flagged[qId];
              
              let styleClasses = "bg-slate-100 text-slate-600 hover:bg-slate-200 border-transparent";
              if (isCurrent) {
                styleClasses = "bg-indigo-600 text-white shadow-md ring-4 ring-indigo-500/20 border-transparent font-black scale-[1.05]";
              } else if (isFlagged) {
                styleClasses = "bg-amber-100 text-amber-800 border-amber-300 font-bold hover:bg-amber-200";
              } else if (isAnswered) {
                styleClasses = "bg-emerald-100 text-emerald-800 border-emerald-200 font-bold hover:bg-emerald-200";
              }

              return (
                <button
                  key={i}
                  onClick={() => setCurrent(i)}
                  className={`h-9 w-9 rounded-xl text-xs font-bold transition-all border cursor-pointer ${styleClasses} flex items-center justify-center relative`}
                >
                  {i + 1}
                  {isFlagged && !isCurrent && (
                    <span className="absolute -top-1 -right-1 h-2 w-2 bg-amber-500 rounded-full" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Quick Stats inside sidebar */}
          <div className="border-t border-slate-100 pt-4 space-y-2 text-xs font-bold text-slate-500">
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-emerald-500" /> Đã trả lời:</span>
              <span className="text-slate-800">{totalAnswered} câu</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-amber-500" /> Cần xem lại:</span>
              <span className="text-slate-800">{Object.values(flagged).filter(Boolean).length} câu</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded bg-slate-300" /> Chưa làm:</span>
              <span className="text-slate-800">{questions.length - totalAnswered} câu</span>
            </div>
          </div>

          {/* Direct submit from sidebar */}
          <button
            onClick={handleSubmit}
            className="w-full flex items-center justify-center gap-1.5 rounded-2xl bg-indigo-50 hover:bg-indigo-100/80 px-4 py-3 text-xs font-bold text-indigo-700 transition-all cursor-pointer border border-indigo-100/60"
          >
            <CheckCircle2 size={14} /> Nộp bài thi
          </button>
        </div>
      </div>
    </div>
  );
}
