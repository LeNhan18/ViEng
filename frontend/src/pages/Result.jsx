import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { submitAnswers } from "../api";
import { CheckCircle2, XCircle, RotateCcw, Loader2, BookOpen, Trophy } from "lucide-react";

export default function Result() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [feedback, setFeedback] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);

  if (!state) return <Navigate to="/exam" />;

  const { config, questions, answers, score } = state;
  const total = questions.length;
  const percentage = Math.round((score / total) * 100);

  const getScoreColor = () => {
    if (percentage >= 80) return "text-green-600";
    if (percentage >= 50) return "text-amber-600";
    return "text-red-600";
  };

  const getScoreBg = () => {
    if (percentage >= 80) return "from-green-500 to-emerald-600";
    if (percentage >= 50) return "from-amber-500 to-orange-600";
    return "from-red-500 to-rose-600";
  };

  async function loadFeedback() {
    setLoadingFeedback(true);
    try {
      const answerList = questions.map((q) => ({
        question_id: q.id,
        user_answer: answers[q.id] || "",
      }));
      const data = await submitAnswers({
        examType: config.examType,
        skill: config.skill,
        answers: answerList,
      });
      setFeedback(data);
    } catch {
      setFeedback(null);
    } finally {
      setLoadingFeedback(false);
    }
  }

  useEffect(() => {
    loadFeedback();
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <div className={`relative overflow-hidden rounded-3xl bg-gradient-to-br ${getScoreBg()} p-8 text-center text-white shadow-xl`}>
        <div className="absolute -right-8 -top-8 h-40 w-40 rounded-full bg-white/10" />
        <div className="absolute -bottom-8 -left-8 h-32 w-32 rounded-full bg-white/10" />
        <div className="relative">
          <Trophy size={48} className="mx-auto mb-4 opacity-90" />
          <div className="mb-2 text-6xl font-extrabold">{percentage}%</div>
          <div className="text-lg font-medium opacity-90">
            {score}/{total} câu đúng
          </div>
          <div className="mt-2 text-sm opacity-75">
            {config.examType.toUpperCase()} • {config.skill} • {config.level}
          </div>
        </div>
      </div>

      <div className="space-y-4">
        <h2 className="text-xl font-bold text-slate-900">Chi tiết từng câu</h2>

        {questions.map((q, i) => {
          const userAnswer = answers[q.id] || "(Chưa trả lời)";
          const correct = q.correct_answer;
          const isCorrect = userAnswer === correct || userAnswer.startsWith(correct);
          const feedbackItem = feedback?.feedbacks?.find((f) => f.question_id === q.id);

          return (
            <div
              key={q.id}
              className={`rounded-2xl border-2 bg-white p-5 shadow-sm ${
                isCorrect ? "border-green-200" : "border-red-200"
              }`}
            >
              <div className="mb-3 flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  {isCorrect ? (
                    <CheckCircle2 size={22} className="mt-0.5 shrink-0 text-green-500" />
                  ) : (
                    <XCircle size={22} className="mt-0.5 shrink-0 text-red-500" />
                  )}
                  <div>
                    <span className="text-sm font-semibold text-slate-500">Câu {i + 1}</span>
                    <p className="text-sm leading-relaxed text-slate-800">{q.content}</p>
                  </div>
                </div>
              </div>

              <div className="ml-9 space-y-2">
                <div className="flex gap-4 text-sm">
                  <span className={`rounded-lg px-3 py-1 font-medium ${isCorrect ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                    Bạn chọn: {userAnswer}
                  </span>
                  {!isCorrect && (
                    <span className="rounded-lg bg-green-50 px-3 py-1 font-medium text-green-700">
                      Đáp án: {correct}
                    </span>
                  )}
                </div>

                {feedbackItem?.explanation && (
                  <div className="mt-3 rounded-xl bg-indigo-50 p-4">
                    <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-indigo-600">
                      <BookOpen size={14} /> Giải thích từ thầy cô AI
                    </div>
                    <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">
                      {feedbackItem.explanation}
                    </p>
                  </div>
                )}

                {!feedbackItem && loadingFeedback && (
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <Loader2 size={14} className="animate-spin" /> Đang lấy giải thích...
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex justify-center gap-4 pb-8">
        <button
          onClick={() => navigate("/exam")}
          className="flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white shadow-md transition-all hover:bg-indigo-700"
        >
          <RotateCcw size={16} /> Làm bài mới
        </button>
      </div>
    </div>
  );
}
