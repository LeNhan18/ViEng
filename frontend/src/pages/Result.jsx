import { useLocation, useNavigate, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { submitAnswers } from "../api";
import { CheckCircle2, XCircle, RotateCcw, Loader2, BookOpen, Trophy, MessageSquare, HelpCircle, Check, X } from "lucide-react";

export default function Result() {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [feedback, setFeedback] = useState(null);
  const [loadingFeedback, setLoadingFeedback] = useState(false);
  const [filterMode, setFilterMode] = useState("all"); // all | correct | incorrect

  if (!state) return <Navigate to="/exam" />;

  const { config, questions, answers, score, readingSection } = state;
  const total = questions.length;
  const percentage = Math.round((score / total) * 100);

  const getScoreColor = () => {
    if (percentage >= 80) return "text-green-600";
    if (percentage >= 50) return "text-amber-600";
    return "text-red-600";
  };

  const getScoreBg = () => {
    if (percentage >= 80) return "from-emerald-500 to-teal-600 shadow-emerald-500/20";
    if (percentage >= 50) return "from-amber-500 to-orange-600 shadow-amber-500/20";
    return "from-rose-500 to-red-600 shadow-rose-500/20";
  };

  const getScoreComment = () => {
    if (percentage >= 80) return "Tuyệt vời! Bạn đã làm chủ kiến thức phần này.";
    if (percentage >= 50) return "Khá tốt! Hãy cố gắng luyện thêm để bứt phá.";
    return "Cần cố gắng thêm! Hãy xem kỹ giải thích để tránh lặp lại lỗi sai.";
  };

  function findPassageForQuestion(questionId) {
    if (!readingSection || !config.part) return null;
    const part = config.part;

    if (part === "part6" && readingSection.part6) {
      for (const p of readingSection.part6) {
        if (p.questions?.some((pq) => pq.id === questionId)) {
          return p.passage || "";
        }
      }
    }

    const part7list = part === "part7_single" ? readingSection.part7_single : readingSection.part7_multiple;
    if (part7list) {
      for (const p of part7list) {
        if (p.questions?.some((pq) => pq.id === questionId)) {
          return Array.isArray(p.passages) ? p.passages.join("\n\n") : p.passages || "";
        }
      }
    }
    return null;
  }

  async function loadFeedback() {
    setLoadingFeedback(true);
    try {
      const answerList = questions.map((q) => {
        const passage = findPassageForQuestion(q.id);
        return {
          question_id: q.id,
          user_answer: answers[q.id] || "",
          question_content: q.content || "",
          correct_answer: q.correct_answer || "",
          options: q.options || [],
          passage: passage || "",
        };
      });
      const data = await submitAnswers({
        examType: config.examType,
        skill: config.skill,
        answers: answerList,
        part: config.part,
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

  // Filter logic
  const filteredQuestions = questions.filter((q) => {
    const userAnswer = answers[q.id] || "";
    const correct = q.correct_answer;
    const isCorrect = userAnswer === correct || userAnswer.startsWith(correct);
    if (filterMode === "correct") return isCorrect;
    if (filterMode === "incorrect") return !isCorrect;
    return true;
  });

  const handleAskAiAboutQuestion = (q, originalIndex) => {
    const userAnswer = answers[q.id] || "(Chưa trả lời)";
    const passage = findPassageForQuestion(q.id);
    const correct = q.correct_answer;

    const prompt = `Chào bạn, mình vừa hoàn thành đề luyện thi ${config.examType.toUpperCase()} ${config.skill} và gặp khó khăn ở câu hỏi này. Mình muốn nhờ bạn giải thích sâu hơn giúp mình:\n\n- **Đề bài (Câu ${originalIndex + 1})**: "${q.content}"\n${
      passage ? `- **Đoạn văn đi kèm**: "${passage}"\n` : ""
    }- **Các phương án lựa chọn**:\n${q.options.map((opt) => `  * ${opt}`).join("\n")}\n- **Đáp án đúng**: "${correct}"\n- **Đáp án mình chọn**: "${userAnswer}"\n\nGiải thích chi tiết tại sao phương án mình chọn chưa đúng và cách suy luận từ vựng/ngữ pháp để chọn ra đáp án đúng giúp mình nhé!`;

    navigate("/chat", { state: { initialMessage: prompt } });
  };

  return (
    <div className="mx-auto max-w-4xl space-y-8 py-4">
      {/* Score Presentation Card */}
      <div className={`relative overflow-hidden rounded-3xl bg-gradient-to-br ${getScoreBg()} p-8 text-center text-white shadow-2xl`}>
        {/* Decorative elements */}
        <div className="absolute -right-12 -top-12 h-48 w-48 rounded-full bg-white/10 blur-xl" />
        <div className="absolute -bottom-12 -left-12 h-40 w-40 rounded-full bg-white/10 blur-xl" />
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:24px_24px] opacity-35" />

        <div className="relative z-10 space-y-3">
          <Trophy size={48} className="mx-auto text-amber-200 animate-float" />
          <div className="text-6xl font-black tracking-tight">{percentage}%</div>
          <div className="text-lg font-bold opacity-90">
            Đúng {score} trên {total} câu
          </div>
          <p className="text-xs text-white/80 font-bold bg-white/10 inline-block px-3 py-1 rounded-full border border-white/10 uppercase tracking-wider">
            {config.examType} • {config.skill} • {config.level}
          </p>
          <div className="pt-2 text-sm font-semibold text-white/90">
            {getScoreComment()}
          </div>
        </div>
      </div>

      {/* Review Section */}
      <div className="space-y-6">
        {/* Navigation & Filters header */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-b border-slate-200 pb-4">
          <h2 className="text-lg font-extrabold text-slate-800 flex items-center gap-2">
            <HelpCircle size={18} className="text-indigo-600" />
            <span>Chi tiết từng câu hỏi</span>
          </h2>

          {/* Filters */}
          <div className="inline-flex rounded-xl bg-slate-100 p-1 border border-slate-200/60">
            {[
              { mode: "all", label: "Tất cả", icon: HelpCircle },
              { mode: "correct", label: "Câu đúng", icon: Check, color: "text-green-500" },
              { mode: "incorrect", label: "Câu sai", icon: X, color: "text-red-500" },
            ].map(({ mode, label, icon: Icon, color }) => (
              <button
                key={mode}
                onClick={() => setFilterMode(mode)}
                className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-xs font-bold transition-all cursor-pointer ${
                  filterMode === mode
                    ? "bg-white text-slate-800 shadow-sm"
                    : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {color ? <span className={color}>●</span> : null}
                <span>{label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Question Cards */}
        {filteredQuestions.length === 0 ? (
          <div className="text-center py-12 border border-dashed border-slate-200 rounded-3xl bg-white text-slate-400 font-semibold">
            Không có câu hỏi nào khớp với bộ lọc của bạn.
          </div>
        ) : (
          <div className="space-y-4">
            {filteredQuestions.map((q) => {
              const originalIndex = questions.findIndex((origQ) => origQ.id === q.id);
              const userAnswer = answers[q.id] || "(Chưa trả lời)";
              const correct = q.correct_answer;
              const isCorrect = userAnswer === correct || userAnswer.startsWith(correct);
              const feedbackItem = feedback?.feedbacks?.find((f) => f.question_id === q.id);

              return (
                <div
                  key={q.id}
                  className={`rounded-3xl border-2 bg-white p-5 shadow-sm transition-all animate-fade-in-up ${
                    isCorrect ? "border-green-100 shadow-green-500/2" : "border-red-100 shadow-red-500/2"
                  }`}
                >
                  <div className="flex items-start gap-4">
                    {/* Icon indicating status */}
                    <div className="mt-0.5 shrink-0">
                      {isCorrect ? (
                        <div className="h-7 w-7 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100 flex items-center justify-center">
                          <CheckCircle2 size={16} />
                        </div>
                      ) : (
                        <div className="h-7 w-7 rounded-full bg-rose-50 text-rose-600 border border-rose-100 flex items-center justify-center">
                          <XCircle size={16} />
                        </div>
                      )}
                    </div>

                    <div className="flex-1 space-y-3">
                      <div className="space-y-1">
                        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">
                          Câu hỏi {originalIndex + 1}
                        </span>
                        <p className="text-sm md:text-base font-bold leading-relaxed text-slate-800">
                          {q.content}
                        </p>
                      </div>

                      {/* Display options for visual review */}
                      {q.options && (
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                          {q.options.map((opt) => {
                            const isUserChoice = userAnswer === opt;
                            const isCorrectChoice = opt === correct || opt.startsWith(correct);
                            
                            let optStyle = "bg-slate-50 border-slate-100 text-slate-600";
                            if (isCorrectChoice) {
                              optStyle = "bg-emerald-50 border-emerald-200 text-emerald-800 font-bold";
                            } else if (isUserChoice) {
                              optStyle = "bg-rose-50 border-rose-200 text-rose-800 font-bold";
                            }

                            return (
                              <div
                                key={opt}
                                className={`rounded-xl border p-3 text-xs leading-relaxed ${optStyle}`}
                              >
                                <span className="mr-1">{isCorrectChoice ? "✓" : isUserChoice ? "✗" : "○"}</span> {opt}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Answer Comparison row */}
                      <div className="flex flex-wrap gap-2 pt-2">
                        <span className={`rounded-lg border px-3 py-1.5 text-xs font-bold ${
                          isCorrect 
                            ? "bg-emerald-50 border-emerald-100 text-emerald-800" 
                            : "bg-rose-50 border-rose-100 text-rose-800"
                        }`}>
                          Bạn chọn: {userAnswer}
                        </span>
                        
                        {!isCorrect && (
                          <span className="rounded-lg border bg-emerald-50 border-emerald-100 px-3 py-1.5 text-xs font-bold text-emerald-800">
                            Đáp án đúng: {correct}
                          </span>
                        )}
                      </div>

                      {/* AI Teacher explanation block */}
                      {feedbackItem?.explanation && (
                        <div className="mt-4 rounded-2xl bg-indigo-50/50 border border-indigo-100/50 p-4.5 space-y-3">
                          <div className="flex items-center gap-1.5 text-xs font-extrabold text-indigo-700 uppercase tracking-wider">
                            <BookOpen size={14} />
                            <span>Giải thích chi tiết của Thầy Cô AI</span>
                          </div>
                          
                          <p className="whitespace-pre-line text-xs md:text-sm leading-relaxed text-slate-700 font-medium">
                            {feedbackItem.explanation}
                          </p>

                          {/* Ask AI interaction button */}
                          <div className="pt-2">
                            <button
                              onClick={() => handleAskAiAboutQuestion(q, originalIndex)}
                              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3.5 py-2 text-xs font-bold text-white shadow shadow-indigo-600/10 transition-all cursor-pointer hover:scale-[1.01]"
                            >
                              <MessageSquare size={13} />
                              Hỏi AI thêm về câu này
                            </button>
                          </div>
                        </div>
                      )}

                      {!feedbackItem && loadingFeedback && (
                        <div className="flex items-center gap-2 text-xs font-bold text-slate-400 py-3 bg-slate-50/50 rounded-2xl border border-slate-100 px-4">
                          <Loader2 size={13} className="animate-spin text-indigo-600" />
                          <span>Đang kết nối thư viện để sinh giải thích...</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer controls */}
      <div className="flex justify-center gap-4 pb-8">
        <button
          onClick={() => navigate("/exam")}
          className="flex items-center gap-1.5 rounded-2xl bg-indigo-600 hover:bg-indigo-500 px-6 py-3.5 text-sm font-bold text-white shadow-lg shadow-indigo-600/10 transition-all cursor-pointer hover:scale-[1.02] active:scale-95"
        >
          <RotateCcw size={16} /> Làm đề thi mới
        </button>
      </div>
    </div>
  );
}
