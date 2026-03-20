import { useState, useRef, useEffect } from "react";
import { chat } from "../api";
import { Send, Loader2, MessageCircle, BookOpen } from "lucide-react";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError("");
    const userMsg = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const data = await chat({ message: text, history });
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.message, sources: data.sources || [] },
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || "Không thể gửi tin nhắn. Vui lòng thử lại.");
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="text-center">
        <h1 className="text-3xl font-bold text-slate-900">Chatbot ViEng</h1>
        <p className="mt-2 text-slate-500">
          Hỏi đáp ngữ pháp, từ vựng TOEIC/IELTS — AI trả lời dựa trên knowledge base
        </p>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex h-[480px] flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-slate-400">
                <MessageCircle size={48} />
                <p className="text-sm">Hỏi bất kỳ câu hỏi nào về ngữ pháp, từ vựng TOEIC/IELTS</p>
                <p className="text-xs">Ví dụ: &quot;Present perfect khác gì past simple?&quot;</p>
              </div>
            )}

            {messages.map((m, i) => (
              <div
                key={i}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                    m.role === "user"
                      ? "bg-indigo-600 text-white"
                      : "bg-slate-100 text-slate-800"
                  }`}
                >
                  <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</p>
                  {m.sources?.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {m.sources.map((s, j) => (
                        <span
                          key={j}
                          className="inline-flex items-center gap-1 rounded bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700"
                        >
                          <BookOpen size={12} /> {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="flex items-center gap-2 rounded-2xl bg-slate-100 px-4 py-3">
                  <Loader2 size={18} className="animate-spin text-indigo-600" />
                  <span className="text-sm text-slate-500">Đang suy nghĩ...</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {error && (
            <div className="mx-4 mb-2 rounded-xl bg-red-50 px-4 py-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <div className="border-t border-slate-100 p-4">
            <div className="flex gap-3">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder="Nhập câu hỏi..."
                className="flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
                disabled={loading}
              />
              <button
                onClick={handleSend}
                disabled={loading || !input.trim()}
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-600 text-white transition-all hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send size={20} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
