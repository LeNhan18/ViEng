import { useState, useRef } from "react";
import { translateText, getTtsAudioUrl } from "../api";
import { ArrowRightLeft, Loader2, BookOpen, Lightbulb, Copy, Check, Volume2 } from "lucide-react";

const DIRECTIONS = [
  { value: "en_to_vi", from: "English", to: "Tiếng Việt", flag: "🇬🇧 → 🇻🇳" },
  { value: "vi_to_en", from: "Tiếng Việt", to: "English", flag: "🇻🇳 → 🇬🇧" },
];

const LEVELS = [
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

export default function Translate() {
  const [text, setText] = useState("");
  const [direction, setDirection] = useState("en_to_vi");
  const [level, setLevel] = useState("intermediate");
  const [useRag, setUseRag] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [ttsLoading, setTtsLoading] = useState(false);
  const audioRef = useRef(null);

  const dirInfo = DIRECTIONS.find((d) => d.value === direction);

  function handleSwap() {
    setDirection((d) => (d === "en_to_vi" ? "vi_to_en" : "en_to_vi"));
    if (result) {
      setText(result.translated);
      setResult(null);
    }
  }

  async function handleTranslate() {
    if (!text.trim()) return;
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const data = await translateText({ text, direction, level, useRag });
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Không thể dịch. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  function handleCopy() {
    if (result?.translated) {
      navigator.clipboard.writeText(result.translated);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
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
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-slate-900">Dịch thuật AI</h1>
        <p className="mt-2 text-slate-500">
          Dịch Anh-Việt thông minh, kèm giải thích từ vựng và ngữ pháp
        </p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        {/* Direction bar */}
        <div className="flex items-center justify-center gap-4 border-b border-slate-100 px-6 py-4">
          <span className="text-sm font-semibold text-slate-700">{dirInfo.from}</span>
          <button
            onClick={handleSwap}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-indigo-100 text-indigo-600 transition-all hover:bg-indigo-200 hover:scale-110 active:scale-95"
            title="Đổi chiều dịch"
          >
            <ArrowRightLeft size={18} />
          </button>
          <span className="text-sm font-semibold text-slate-700">{dirInfo.to}</span>
        </div>

        {/* Input / Output */}
        <div className="grid md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-100">
          <div className="p-4">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={direction === "en_to_vi" ? "Enter English text..." : "Nhập văn bản tiếng Việt..."}
              rows={6}
              className="w-full resize-none border-0 bg-transparent text-sm leading-relaxed text-slate-800 placeholder-slate-400 focus:outline-none"
              maxLength={5000}
            />
            <div className="flex items-center justify-between pt-2 text-xs text-slate-400">
              <span>{text.length}/5000</span>
            </div>
          </div>

          <div className="relative p-4 bg-slate-50/50">
            {loading ? (
              <div className="flex h-full min-h-[140px] items-center justify-center">
                <Loader2 size={24} className="animate-spin text-indigo-500" />
                <span className="ml-2 text-sm text-slate-500">Đang dịch...</span>
              </div>
            ) : result ? (
              <div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
                  {result.translated}
                </p>
                {direction === "vi_to_en" && result.translated.trim() && (
                  <button
                    onClick={handlePlayPronunciation}
                    disabled={ttsLoading}
                    className="mt-3 flex items-center gap-2 rounded-lg bg-indigo-100 px-3 py-2 text-xs font-medium text-indigo-700 transition-all hover:bg-indigo-200 disabled:opacity-50"
                    title="Nghe phát âm"
                  >
                    {ttsLoading ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Volume2 size={14} />
                    )}
                    Đọc phát âm
                  </button>
                )}
                <button
                  onClick={handleCopy}
                  className="absolute right-4 top-4 flex items-center gap-1 rounded-lg bg-white px-2.5 py-1.5 text-xs font-medium text-slate-500 shadow-sm transition-all hover:text-indigo-600"
                >
                  {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                  {copied ? "Đã copy" : "Copy"}
                </button>
                <audio ref={audioRef} className="hidden" />
              </div>
            ) : (
              <div className="flex h-full min-h-[140px] items-center justify-center text-sm text-slate-400">
                Bản dịch sẽ hiện ở đây
              </div>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 px-6 py-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-slate-500">Trình độ:</span>
              {LEVELS.map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => setLevel(value)}
                  className={`rounded-lg px-3 py-1 text-xs font-medium transition-all ${
                    level === value
                      ? "bg-indigo-100 text-indigo-700"
                      : "text-slate-400 hover:text-slate-600"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={useRag}
                onChange={(e) => setUseRag(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-indigo-600 accent-indigo-600"
              />
              <span className="font-medium text-slate-500">Dùng Knowledge Base</span>
            </label>
          </div>

          <button
            onClick={handleTranslate}
            disabled={loading || !text.trim()}
            className="flex items-center gap-2 rounded-xl bg-indigo-600 px-6 py-2.5 text-sm font-bold text-white shadow-md shadow-indigo-200 transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRightLeft size={16} />}
            Dịch
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      {/* Vocabulary + Grammar Notes */}
      {result && (result.vocabulary?.length > 0 || result.grammar_notes?.length > 0) && (
        <div className="grid gap-6 md:grid-cols-2">
          {result.vocabulary?.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2">
                <BookOpen size={18} className="text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">Từ vựng quan trọng</h3>
              </div>
              <div className="space-y-3">
                {result.vocabulary.map((v, i) => (
                  <div key={i} className="rounded-xl bg-slate-50 p-3">
                    <div className="flex items-baseline gap-2">
                      <span className="font-semibold text-indigo-700">{v.word}</span>
                      <span className="text-sm text-slate-600">— {v.meaning}</span>
                    </div>
                    {v.example && (
                      <p className="mt-1 text-xs italic text-slate-500">{v.example}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {result.grammar_notes?.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="mb-4 flex items-center gap-2">
                <Lightbulb size={18} className="text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">Ghi chú ngữ pháp</h3>
              </div>
              <ul className="space-y-2">
                {result.grammar_notes.map((note, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-700">
                    <span className="mt-0.5 h-5 w-5 shrink-0 rounded-full bg-amber-100 text-center text-xs font-bold leading-5 text-amber-700">
                      {i + 1}
                    </span>
                    {note}
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
