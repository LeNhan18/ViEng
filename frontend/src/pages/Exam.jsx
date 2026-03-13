import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { generateTest } from "../api";
import { Loader2, ChevronRight, ChevronLeft, CheckCircle2, BookOpen } from "lucide-react";

const EXAM_TYPES = [
  { value: "toeic", label: "TOEIC", color: "border-blue-500 bg-blue-50 text-blue-700" },
  { value: "ielts", label: "IELTS", color: "border-green-500 bg-green-50 text-green-700" },
];

const SKILLS = [
  { value: "reading", label: "Reading" },
  { value: "listening", label: "Listening" },
  { value: "writing", label: "Writing" },
  { value: "speaking", label: "Speaking" },
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
    numQuestions: 5,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [questions, setQuestions] = useState([]);
  const [current, setCurrent] = useState(0);
  const [answers, setAnswers] = useState({});

  async function handleGenerate() {
    setLoading(true);
    setError("");
    try {
      const data = await generateTest(config);
      setQuestions(data.questions);
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
    const resultData = {
      config,
      questions,
      answers,
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
          <p className="mt-2 text-slate-500">Chọn kỳ thi, kỹ năng và trình độ để AI tạo đề cho bạn</p>
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

          <div>
            <label className="mb-3 block text-sm font-semibold text-slate-700">Kỹ năng</label>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {SKILLS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setConfig((c) => ({ ...c, skill: value }))}
                  className={`rounded-xl border-2 px-4 py-3 text-sm font-medium transition-all ${
                    config.skill === value
                      ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                      : "border-slate-200 text-slate-500 hover:border-slate-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

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
              min={3}
              max={15}
              value={config.numQuestions}
              onChange={(e) => setConfig((c) => ({ ...c, numQuestions: +e.target.value }))}
              className="w-full accent-indigo-600"
            />
            <div className="flex justify-between text-xs text-slate-400">
              <span>3</span>
              <span>15</span>
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

  const q = questions[current];
  const totalAnswered = Object.keys(answers).length;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold text-slate-900">
          {config.examType.toUpperCase()} — {config.skill} — {config.level}
        </h2>
        <span className="rounded-full bg-indigo-100 px-3 py-1 text-sm font-medium text-indigo-700">
          {totalAnswered}/{questions.length} đã trả lời
        </span>
      </div>

      <div className="flex gap-2">
        {questions.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrent(i)}
            className={`h-10 w-10 rounded-lg text-sm font-semibold transition-all ${
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
