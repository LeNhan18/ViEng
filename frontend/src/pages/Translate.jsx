import { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { translateText, getTtsAudioUrl } from "../api";
import { ArrowRightLeft, Loader2, BookOpen, Lightbulb, Copy, Check, Volume2, MessageSquare, Sparkles, RefreshCw } from "lucide-react";
import LlmProviderSelect from "../components/LlmProviderSelect";

const DIRECTIONS = [
  { value: "en_to_vi", from: "English", to: "Tiếng Việt", flag: "🇺🇸 English" },
  { value: "vi_to_en", from: "Tiếng Việt", to: "English", flag: "🇻🇳 Tiếng Việt" },
];

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

const SAMPLE_SENTENCES = [
  { text: "The candidate answered all questions confidently during the interview.", direction: "en_to_vi", label: "TOEIC/IELTS Interview" },
  { text: "Mặc dù thời tiết không thuận lợi, trận đấu vẫn được diễn ra.", direction: "vi_to_en", label: "Mệnh đề nhượng bộ" },
  { text: "In order to achieve high scores in IELTS, regular practice is essential.", direction: "en_to_vi", label: "Mục đích / Khuyên nhủ" },
];

export default function Translate() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [direction, setDirection] = useState("en_to_vi");
  const [level, setLevel] = useState("intermediate");
  const [useRag, setUseRag] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [llmProvider, setLlmProvider] = useState(localStorage.getItem("vieng_llm_provider") || "groq");
  const [isSwapping, setIsSwapping] = useState(false);
  const audioRef = useRef(null);

  const dirInfo = DIRECTIONS.find((d) => d.value === direction);
  const targetDirInfo = DIRECTIONS.find((d) => d.value !== direction);

  function handleSwap() {
    setIsSwapping(true);
    setTimeout(() => setIsSwapping(false), 300);
    
    setDirection((d) => (d === "en_to_vi" ? "vi_to_en" : "en_to_vi"));
    if (result) {
      setText(result.translated);
      setResult(null);
    }
  }

  async function performTranslation(currentText, currentDirection, currentLevel, currentUseRag) {
    if (!currentText.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      localStorage.setItem("vieng_llm_provider", llmProvider);
      const data = await translateText({ 
        text: currentText, 
        direction: currentDirection, 
        level: currentLevel, 
        useRag: currentUseRag, 
        llmProvider 
      });
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Không thể dịch. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTranslate() {
    await performTranslation(text, direction, level, useRag);
  }

  function handleSelectSample(sample) {
    setDirection(sample.direction);
    setText(sample.text);
    performTranslation(sample.text, sample.direction, level, useRag);
  }

  function handleCopy() {
    if (result?.translated) {
      navigator.clipboard.writeText(result.translated);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  function handleAskAiDeep() {
    if (!text.trim() || !result?.translated) return;
    navigate("/chat", {
      state: {
        initialMessage: `Chào bạn, mình vừa dịch câu này trên hệ thống và muốn được giải thích sâu hơn về cấu trúc ngữ pháp, từ vựng và cách dùng của nó:\n\n- **Văn bản gốc**: "${text}"\n- **Bản dịch gợi ý**: "${result.translated}"\n\nGiải thích chi tiết các điểm đáng học giúp mình nhé!`,
      },
    });
  }

  async function handlePlayPronunciation() {
    if (!result?.translated || ttsLoading) return;
    setTtsLoading(true);
    try {
      const url = await getTtsAudioUrl(result.translated);
      if (audioRef.current) {
        audioRef.current.src = url;
        audioRef.current.onended = () => URL.revokeObjectURL(url);
        await audioRef.current.play();
      }
    } catch {
      // ignore
    } finally {
      setTtsLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8 py-4">
      {/* Title */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
          <Sparkles size={12} className="text-emerald-600 animate-pulse" />
          <span>Bản dịch thông minh chuẩn ngữ cảnh</span>
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 md:text-4xl">Dịch Thuật AI</h1>
        <p className="text-slate-500 max-w-lg mx-auto text-sm md:text-base">
          Dịch thuật đa chiều kết hợp giải thích từ vựng cốt lõi và ngữ pháp chuyên sâu qua cơ sở dữ liệu.
        </p>
      </div>

      {/* Main Box */}
      <div className="rounded-3xl border border-slate-200/80 bg-white shadow-xl shadow-slate-100 overflow-hidden">
        {/* Top bar with model select */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/50 px-6 py-4">
          <div className="text-sm font-bold text-slate-700">Cấu hình mô hình dịch</div>
          <LlmProviderSelect value={llmProvider} onChange={setLlmProvider} />
        </div>

        {/* Direction Select Bar */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-3 bg-white">
          <div className="text-sm font-bold text-indigo-600 px-3 py-1.5 rounded-lg bg-indigo-50/60">
            {dirInfo.flag}
          </div>
          
          <button
            onClick={handleSwap}
            className={`flex h-10 w-10 items-center justify-center rounded-full bg-indigo-50 text-indigo-600 transition-all hover:bg-indigo-100 hover:scale-110 active:scale-95 cursor-pointer ${
              isSwapping ? "rotate-180" : ""
            } duration-300`}
            title="Đổi chiều dịch"
          >
            <ArrowRightLeft size={18} />
          </button>
          
          <div className="text-sm font-bold text-indigo-600 px-3 py-1.5 rounded-lg bg-indigo-50/60">
            {targetDirInfo.flag}
          </div>
        </div>

        {/* Input/Output Workspace */}
        <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100 min-h-[220px]">
          {/* Left: Input Textarea */}
          <div className="p-5 flex flex-col justify-between">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={direction === "en_to_vi" ? "Nhập văn bản tiếng Anh cần dịch..." : "Nhập văn bản tiếng Việt..."}
              rows={7}
              className="w-full resize-none border-0 bg-transparent p-0 text-sm leading-relaxed text-slate-800 placeholder-slate-400 outline-none focus:ring-0"
              maxLength={5000}
            />
            <div className="flex items-center justify-between pt-3 border-t border-slate-50 text-xs text-slate-400 font-medium">
              <span>{text.length}/5000 ký tự</span>
              {text.trim() && (
                <button 
                  onClick={() => setText("")}
                  className="hover:text-rose-500 transition-colors cursor-pointer"
                >
                  Xóa sạch
                </button>
              )}
            </div>
          </div>

          {/* Right: Output Translation */}
          <div className="relative p-5 bg-slate-50/40 flex flex-col justify-between">
            {loading ? (
              <div className="flex h-full min-h-[160px] flex-col items-center justify-center gap-2">
                <Loader2 size={28} className="animate-spin text-indigo-600" />
                <span className="text-xs font-semibold text-slate-500 animate-pulse">AI đang phân tích và dịch nghĩa...</span>
              </div>
            ) : result ? (
              <div className="h-full flex flex-col justify-between">
                <div className="space-y-4">
                  <p className="whitespace-pre-wrap text-sm font-medium leading-relaxed text-slate-800">
                    {result.translated}
                  </p>
                  
                  <div className="flex flex-wrap gap-2 pt-2">
                    {direction === "vi_to_en" && result.translated.trim() && (
                      <button
                        onClick={handlePlayPronunciation}
                        disabled={ttsLoading}
                        className="flex items-center gap-1.5 rounded-lg bg-indigo-50 border border-indigo-100/60 px-3 py-1.5 text-xs font-bold text-indigo-700 transition-all hover:bg-indigo-100 disabled:opacity-50 cursor-pointer"
                      >
                        {ttsLoading ? (
                          <Loader2 size={13} className="animate-spin" />
                        ) : (
                          <Volume2 size={13} />
                        )}
                        Nghe phát âm
                      </button>
                    )}

                    <button
                      onClick={handleAskAiDeep}
                      className="flex items-center gap-1.5 rounded-lg bg-emerald-50 border border-emerald-100/60 px-3 py-1.5 text-xs font-bold text-emerald-700 transition-all hover:bg-emerald-100 cursor-pointer"
                      title="Chuyển đoạn dịch này qua Chatbot để hỏi sâu hơn về ngữ pháp"
                    >
                      <MessageSquare size={13} />
                      Hỏi AI giải thích sâu
                    </button>
                  </div>
                </div>

                <div className="flex justify-end pt-3 border-t border-slate-50">
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 rounded-lg bg-white border border-slate-200 px-3 py-1.5 text-xs font-bold text-slate-600 shadow-sm transition-all hover:border-slate-300 hover:text-indigo-600 cursor-pointer"
                  >
                    {copied ? <Check size={13} className="text-green-500" /> : <Copy size={13} />}
                    {copied ? "Đã sao chép" : "Sao chép"}
                  </button>
                  <audio ref={audioRef} className="hidden" />
                </div>
              </div>
            ) : (
              <div className="flex h-full min-h-[160px] items-center justify-center text-sm text-slate-400 font-medium">
                Bản dịch tiếng {direction === "en_to_vi" ? "Việt" : "Anh"} của bạn sẽ hiển thị ở đây.
              </div>
            )}
          </div>
        </div>

        {/* Controls footer */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-slate-100 bg-slate-50/50 px-6 py-4">
          <div className="flex flex-wrap items-center gap-5">
            {/* Level select */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-500">Giọng văn:</span>
              <div className="inline-flex rounded-lg bg-white p-0.5 border border-slate-200">
                {LEVELS.map(({ value, label }) => (
                  <button
                    key={value}
                    onClick={() => setLevel(value)}
                    className={`rounded-md px-3 py-1.5 text-xs font-bold transition-all cursor-pointer ${
                      level === value
                        ? "bg-indigo-600 text-white shadow-sm"
                        : "text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Knowledge base checkbox */}
            <label className="flex items-center gap-2 text-xs font-bold text-slate-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={useRag}
                onChange={(e) => setUseRag(e.target.checked)}
                className="h-4.5 w-4.5 rounded border-slate-300 text-indigo-600 accent-indigo-600 focus:ring-indigo-500"
              />
              <span>Sử dụng Knowledge Base (RAG)</span>
            </label>
          </div>

          <button
            onClick={handleTranslate}
            disabled={loading || !text.trim()}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 px-6 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-600/20 transition-all hover:scale-[1.02] active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
            Dịch ngay
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50/70 p-4 text-sm font-medium text-red-700 animate-fade-in-up">
          {error}
        </div>
      )}

      {/* Suggested Samples */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-slate-500">Câu mẫu gợi ý thử nghiệm:</h3>
        <div className="flex flex-wrap gap-2">
          {SAMPLE_SENTENCES.map((sample, i) => (
            <button
              key={i}
              onClick={() => handleSelectSample(sample)}
              className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-left text-xs font-semibold text-slate-700 hover:border-indigo-400 hover:bg-indigo-50/20 transition-all cursor-pointer shadow-sm"
            >
              <span className="text-[10px] uppercase font-bold text-indigo-600 block mb-0.5">{sample.label}</span>
              <span className="line-clamp-1">{sample.text}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Vocabulary + Grammar Notes */}
      {result && (result.vocabulary?.length > 0 || result.grammar_notes?.length > 0) && (
        <div className="grid gap-6 md:grid-cols-2 animate-fade-in-up">
          {/* Vocabulary Card */}
          {result.vocabulary?.length > 0 && (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-100">
                <div className="rounded-lg bg-indigo-50 p-2 text-indigo-600">
                  <BookOpen size={18} />
                </div>
                <h3 className="text-sm font-bold text-slate-900">Từ vựng quan trọng cần nhớ</h3>
              </div>
              <div className="space-y-3 max-h-[350px] overflow-y-auto pr-1">
                {result.vocabulary.map((v, i) => (
                  <div key={i} className="rounded-2xl border border-slate-100 bg-slate-50/50 p-4 space-y-1">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-extrabold text-indigo-700">{v.word}</span>
                      <span className="text-xs font-semibold text-slate-500">— {v.meaning}</span>
                    </div>
                    {v.example && (
                      <p className="text-xs italic text-slate-500 border-l-2 border-slate-200 pl-2 mt-1">
                        Ví dụ: {v.example}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Grammar Card */}
          {result.grammar_notes?.length > 0 && (
            <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-100">
                <div className="rounded-lg bg-amber-50 p-2 text-amber-600">
                  <Lightbulb size={18} />
                </div>
                <h3 className="text-sm font-bold text-slate-900">Cấu trúc ngữ pháp trọng tâm</h3>
              </div>
              <ul className="space-y-3 max-h-[350px] overflow-y-auto pr-1">
                {result.grammar_notes.map((note, i) => (
                  <li key={i} className="flex gap-3 text-sm text-slate-700 items-start rounded-2xl bg-amber-50/20 border border-amber-100/30 p-4">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-xs font-bold text-amber-800 mt-0.5">
                      {i + 1}
                    </span>
                    <span className="leading-relaxed font-semibold">{note}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
