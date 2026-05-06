import { useState, useRef, useEffect } from "react";
import { chat, chatWithOcr } from "../api";
import {
  Send,
  Loader2,
  MessageCircle,
  BookOpen,
  Paperclip,
  X,
  FileText,
  Image as ImageIcon,
} from "lucide-react";
import LlmProviderSelect from "../components/LlmProviderSelect";

const MAX_FILE_MB = 10;
const ACCEPTED = "image/png,image/jpeg,image/jpg,image/webp,image/bmp,image/tiff,application/pdf";

export default function Chat() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [llmProvider, setLlmProvider] = useState(localStorage.getItem("vieng_llm_provider") || "groq");
  const [attachedFile, setAttachedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const fileInputRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  function handlePickFile(e) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (f.size > MAX_FILE_MB * 1024 * 1024) {
      setError(`File vượt quá ${MAX_FILE_MB}MB.`);
      return;
    }
    setError("");
    setAttachedFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    if (f.type.startsWith("image/")) {
      setPreviewUrl(URL.createObjectURL(f));
    } else {
      setPreviewUrl("");
    }
  }

  function clearAttachment() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setAttachedFile(null);
    setPreviewUrl("");
  }

  async function handleSend() {
    const text = input.trim();
    if ((!text && !attachedFile) || loading) return;

    setError("");
    localStorage.setItem("vieng_llm_provider", llmProvider);

    const fileSnapshot = attachedFile;
    const previewSnapshot = previewUrl;
    const userMsg = {
      role: "user",
      content: text || (fileSnapshot ? "(đã gửi file)" : ""),
      attachment: fileSnapshot
        ? {
            name: fileSnapshot.name,
            type: fileSnapshot.type,
            preview: previewSnapshot,
          }
        : null,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setAttachedFile(null);
    setPreviewUrl("");
    setLoading(true);

    try {
      if (fileSnapshot) {
        const data = await chatWithOcr({
          message: text,
          file: fileSnapshot,
          llmProvider,
        });
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.message,
            sources: data.sources || [],
            extracted_text: data.extracted_text || "",
          },
        ]);
      } else {
        const history = messages.map((m) => ({ role: m.role, content: m.content }));
        const data = await chat({ message: text, history, llmProvider });
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.message, sources: data.sources || [] },
        ]);
      }
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
          Hỏi đáp ngữ pháp, từ vựng TOEIC/IELTS — gửi cả ảnh đề / PDF để AI đọc và trả lời
        </p>
        <div className="mt-4 flex justify-center">
          <LlmProviderSelect value={llmProvider} onChange={setLlmProvider} />
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex h-[520px] flex-col">
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 && (
              <div className="flex h-full flex-col items-center justify-center gap-3 text-slate-400">
                <MessageCircle size={48} />
                <p className="text-sm">Hỏi bất kỳ câu hỏi nào về ngữ pháp, từ vựng TOEIC/IELTS</p>
                <p className="text-xs">
                  Hoặc bấm <Paperclip size={12} className="inline" /> để gửi ảnh đề / PDF cho AI đọc giúp
                </p>
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
                  {m.attachment && (
                    <div className="mb-2 flex items-center gap-2 rounded-xl bg-white/10 p-2">
                      {m.attachment.preview ? (
                        <img
                          src={m.attachment.preview}
                          alt={m.attachment.name}
                          className="h-16 w-16 rounded-lg object-cover"
                        />
                      ) : (
                        <FileText size={28} className="text-white/80" />
                      )}
                      <div className="text-xs opacity-90">
                        <div className="font-medium">{m.attachment.name}</div>
                        <div>{m.attachment.type || "file"}</div>
                      </div>
                    </div>
                  )}
                  {m.content && (
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{m.content}</p>
                  )}
                  {m.extracted_text && (
                    <details className="mt-2 rounded-lg bg-white/60 p-2 text-slate-700">
                      <summary className="cursor-pointer text-xs font-medium">
                        Văn bản đã OCR
                      </summary>
                      <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap text-xs">
                        {m.extracted_text}
                      </pre>
                    </details>
                  )}
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
                  <span className="text-sm text-slate-500">
                    {attachedFile || messages[messages.length - 1]?.attachment
                      ? "Đang nhận diện văn bản và suy nghĩ..."
                      : "Đang suy nghĩ..."}
                  </span>
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

          {attachedFile && (
            <div className="mx-4 mb-2 flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-2">
              {previewUrl ? (
                <img
                  src={previewUrl}
                  alt={attachedFile.name}
                  className="h-12 w-12 rounded-lg object-cover"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-100 text-indigo-600">
                  {attachedFile.type === "application/pdf" ? (
                    <FileText size={22} />
                  ) : (
                    <ImageIcon size={22} />
                  )}
                </div>
              )}
              <div className="flex-1 text-sm">
                <div className="font-medium text-slate-800">{attachedFile.name}</div>
                <div className="text-xs text-slate-500">
                  {(attachedFile.size / 1024).toFixed(1)} KB · sẽ được OCR và gửi cho AI
                </div>
              </div>
              <button
                onClick={clearAttachment}
                className="rounded-lg p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-700"
                title="Bỏ file"
                type="button"
              >
                <X size={18} />
              </button>
            </div>
          )}

          <div className="border-t border-slate-100 p-4">
            <div className="flex gap-3">
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED}
                className="hidden"
                onChange={handlePickFile}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={loading}
                title="Đính kèm ảnh hoặc PDF"
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-600 transition-all hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Paperclip size={20} />
              </button>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
                placeholder={
                  attachedFile
                    ? "Hỏi gì về file này? (có thể bỏ trống)"
                    : "Nhập câu hỏi..."
                }
                className="flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
                disabled={loading}
              />
              <button
                onClick={handleSend}
                disabled={loading || (!input.trim() && !attachedFile)}
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
