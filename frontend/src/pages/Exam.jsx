import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { generateTest } from "../api";
import { Loader2, ChevronRight, ChevronLeft, CheckCircle2, BookOpen } from "lucide-react";

const EXAM_TYPES = [
  { value: "toeic", label: "TOEIC", color: "border-blue-500 bg-blue-50 text-blue-700" },
  { value: "ielts", label: "IELTS", color: "border-green-500 bg-green-50 text-green-700" },
];

const TOEIC_READING_PARTS = [
  {
    value: "part5",
    label: "Part 5",
    desc: "Incomplete Sentences",
    detail: "Hoàn thành câu - 30 câu chuẩn",
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
    detail: "Đọc hiểu 1 đoạn - 2-4 câu/bài",
    defaultN: 6,
    maxN: 29,
  },
  {
    value: "part7_multiple",
    label: "Part 7 (Multi)",
    desc: "Multiple Passages",
    detail: "Đọc hiểu 2-3 đoạn liên quan - 5 câu/bộ",
    defaultN: 5,
    maxN: 25,
  },
];

const LEVELS = [
  { value: "beginner", label: "Beginner", desc: "Mới bắt đầu" },
  { value: "intermediate", label: "Intermediate", desc: "Trung cấp" },
  { value: "advanced", label: "Advanced", desc: "Nâng cao" },
];

export default function Exam() {
  const navigate = useNavigate();
  const [step, setStep] = useState("setup");
  const [config, setConfig] = useState({
    examType: "toeic",
    skill: "reading",
    level: "intermediate",
    part: "part5",
    numQuestions: 10,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [testData, setTestData] = useState(null);
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState({});

  const selectedPartInfo = TOEIC_READING_PARTS.find((p) => p.value === config.part);

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
      const data = await generateTest(config);
      setTestData(data);
      setAnswers({});
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
      <div className="mx-auto max-w-2xl space-y-8">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-slate-900">Tạo bài thi</h1>
          <p className="mt-2 text-slate-500">Chọn dạng bài và trình độ để AI tạo đề TOEIC Reading cho bạn</p>
        </div>

        <div className="space-y-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div>
            <label className="mb-3 block text-sm font-semibold text-slate-700">Kỳ thi</label>
            <div className="flex gap-3">
              {EXAM_TYPES.map(({ value, label, color }) => (
                <button
                  key={value}
                  onClick={() => setConfig((c) => ({ ...c, examType: value }))}
                  className={`flex-1 rounded-xl border-2 px-4 py-3 text-center font-semibold transition-all ${
                    config.examType === value ? color : "border-slate-200 bg-white text-slate-400 hover:border-slate-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {config.examType === "toeic" && (
            <div>
              <label className="mb-3 block text-sm font-semibold text-slate-700">Dạng bài Reading</label>
              <div className="grid grid-cols-2 gap-3">
                {TOEIC_READING_PARTS.map(({ value, label, desc, detail }) => (
                  <button
                    key={value}
                    onClick={() => handlePartChange(value)}
                    className={`rounded-xl border-2 px-4 py-3 text-left transition-all ${
                      config.part === value
                        ? "border-blue-500 bg-blue-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className={`text-sm font-bold ${config.part === value ? "text-blue-700" : "text-slate-700"}`}>
                      {label}
                    </div>
                    <div className={`text-xs font-medium ${config.part === value ? "text-blue-600" : "text-slate-500"}`}>
                      {desc}
                    </div>
                    <div className="mt-1 text-xs text-slate-400">{detail}</div>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <label className="mb-3 block text-sm font-semibold text-slate-700">Trình độ</label>
            <div className="grid grid-cols-3 gap-3">
              {LEVELS.map(({ value, label, desc }) => (
                <button
                  key={value}
                  onClick={() => setConfig((c) => ({ ...c, level: value }))}
                  className={`rounded-xl border-2 px-4 py-3 text-left transition-all ${
                    config.level === value
                      ? "border-indigo-500 bg-indigo-50"
                      : "border-slate-200 hover:border-slate-300"
                  }`}
                >
                  <div className={`text-sm font-semibold ${config.level === value ? "text-indigo-700" : "text-slate-700"}`}>
                    {label}
                  </div>
                  <div className="text-xs text-slate-400">{desc}</div>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-3 block text-sm font-semibold text-slate-700">
              Số câu hỏi: <span className="text-indigo-600">{config.numQuestions}</span>
            </label>
            <input
              type="range"
              min={2}
              max={selectedPartInfo?.maxN || 30}
              value={config.numQuestions}
              onChange={(e) => setConfig((c) => ({ ...c, numQuestions: +e.target.value }))}
              className="w-full accent-indigo-600"
            />
            <div className="flex justify-between text-xs text-slate-400">
              <span>2</span>
              <span>{selectedPartInfo?.maxN || 30}</span>
            </div>
          </div>

          {error && (
            <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
          )}

          <button
            onClick={handleGenerate}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-indigo-600 px-6 py-4 text-lg font-bold text-white shadow-lg shadow-indigo-200 transition-all hover:bg-indigo-700 hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                AI đang tạo đề...
              </>
            ) : (
              <>
                <BookOpen size={20} />
                Tạo đề thi
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
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-900">{partLabel}</h2>
          <p className="text-sm text-slate-500">Trình độ: {config.level}</p>
        </div>
        <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-700">
          {totalAnswered}/{questions.length} đã trả lời
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {questions.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            className={`h-9 w-9 rounded-lg text-sm font-semibold transition-all ${
              i === current
                ? "bg-indigo-600 text-white shadow-md"
                : answers[questions[i].id]
                  ? "bg-green-100 text-green-700"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200"
            }`}
          >
            {i + 1}
          </button>
        ))}
      </div>

      {passageInfo && (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
          {passageInfo.type === "part6" && (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">Đoạn văn</div>
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                {passageInfo.passage}
              </div>
            </div>
          )}
          {(passageInfo.type === "part7_single" || passageInfo.type === "part7_multiple") && (
            <div className="space-y-4">
              {passageInfo.passages.map((text, idx) => (
                <div key={idx}>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Đoạn {idx + 1}
                  </div>
                  <div className="whitespace-pre-wrap rounded-xl bg-white p-4 text-sm leading-relaxed text-slate-700 shadow-sm">
                    {text}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {q && (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-1 text-sm font-medium text-indigo-600">
            Câu {current + 1}/{questions.length}
          </div>
          <p className="mb-6 text-lg leading-relaxed text-slate-800">{q.content}</p>

          {q.options && (
            <div className="space-y-3">
              {q.options.map((opt) => {
                const isSelected = answers[q.id] === opt;
                return (
                  <button
                    key={opt}
                    onClick={() => handleSelect(q.id, opt)}
                    className={`flex w-full items-center gap-3 rounded-xl border-2 px-5 py-4 text-left transition-all ${
                      isSelected
                        ? "border-indigo-500 bg-indigo-50 text-indigo-800"
                        : "border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    {isSelected && <CheckCircle2 size={18} className="shrink-0 text-indigo-600" />}
                    <span className={`text-sm ${isSelected ? "font-semibold" : ""}`}>{opt}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between">
        <button
          onClick={() => setCurrent((c) => Math.max(0, c - 1))}
          disabled={current === 0}
          className="flex items-center gap-1 rounded-xl border border-slate-200 px-5 py-3 text-sm font-medium text-slate-600 transition-all hover:bg-slate-50 disabled:opacity-40"
        >
          <ChevronLeft size={16} /> Câu trước
        </button>

        {current < questions.length - 1 ? (
          <button
            onClick={() => setCurrent((c) => Math.min(questions.length - 1, c + 1))}
            className="flex items-center gap-1 rounded-xl bg-indigo-600 px-5 py-3 text-sm font-medium text-white shadow-md transition-all hover:bg-indigo-700"
          >
            Câu tiếp <ChevronRight size={16} />
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={totalAnswered < questions.length}
            className="flex items-center gap-2 rounded-xl bg-green-600 px-6 py-3 text-sm font-bold text-white shadow-md transition-all hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <CheckCircle2 size={16} /> Nộp bài ({totalAnswered}/{questions.length})
          </button>
        )}
      </div>
    </div>
  );
}
