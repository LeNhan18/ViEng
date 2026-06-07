import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { chat, chatWithOcr, getChatHistory, clearChatHistory } from "../api";
import {
  Send,
  Loader2,
  MessageCircle,
  BookOpen,
  Paperclip,
  X,
  FileText,
  Image as ImageIcon,
  Sparkles,
  Bot,
  User,
  Trash2,
} from "lucide-react";
import LlmProviderSelect from "../components/LlmProviderSelect";

const MAX_FILE_MB = 10;
const ACCEPTED = "image/png,image/jpeg,image/jpg,image/webp,image/bmp,image/tiff,application/pdf";

const SUGGESTIONS = [
  "Phân biệt Alternately & Alternatively?",
  "Mẹo tránh bẫy Part 5 TOEIC thường gặp",
  "Cấu trúc đảo ngữ điều kiện loại 3 (Had I known...)",
  "Làm sao cải thiện phát âm IELTS Speaking?"
];

export default function Chat() {
  const location = useLocation();
  const locationStateRef = useRef(location.state);
  
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [llmProvider, setLlmProvider] = useState(localStorage.getItem("vieng_llm_provider") || "groq");
  const [attachedFile, setAttachedFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const fileInputRef = useRef(null);
  const bottomRef = useRef(null);

  // Auto scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  // Handle chat history fetch and forwarded queries
  useEffect(() => {
    async function loadInitialData() {
      const token = localStorage.getItem("vieng_access_token");
      if (token) {
        setLoading(true);
        try {
          const data = await getChatHistory();
          if (data && Array.isArray(data)) {
            setMessages(data);
          }
        } catch (err) {
          console.error("Failed to load chat history", err);
        } finally {
          setLoading(false);
        }
      }

      const state = locationStateRef.current;
      if (state?.initialMessage) {
        // Clear history state
        window.history.replaceState({}, document.title);
        locationStateRef.current = null;
        sendSuggestedMessage(state.initialMessage);
      }
    }
    loadInitialData();
  }, []);

  async function handleClearHistory() {
    if (window.confirm("Bạn có chắc chắn muốn xóa toàn bộ lịch sử chat không?")) {
      setError("");
      setLoading(true);
      try {
        await clearChatHistory();
        setMessages([]);
      } catch (err) {
        setError(err.response?.data?.detail || "Không thể xóa lịch sử chat.");
      } finally {
        setLoading(false);
      }
    }
  }

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

  async function sendSuggestedMessage(msgText) {
    if (loading) return;
    setError("");
    localStorage.setItem("vieng_llm_provider", llmProvider);

    const userMsg = {
      role: "user",
      content: msgText,
      attachment: null,
    };
    
    // We capture history before updating state
    setMessages((prev) => {
      const updated = [...prev, userMsg];
      // Run the network request immediately
      performChatRequest(msgText, null, updated.slice(0, -1));
      return updated;
    });
  }

  async function performChatRequest(text, fileSnapshot, priorMessages) {
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
        const history = priorMessages.map((m) => ({ role: m.role, content: m.content }));
        const data = await chat({ message: text, history, llmProvider });
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.message, sources: data.sources || [] },
        ]);
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Không thể gửi tin nhắn. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
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

    setMessages((prev) => {
      const updated = [...prev, userMsg];
      performChatRequest(text, fileSnapshot, updated.slice(0, -1));
      return updated;
    });

    setInput("");
    setAttachedFile(null);
    setPreviewUrl("");
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 py-4">
      {/* Title */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700">
          <Sparkles size={12} className="text-indigo-600 animate-pulse" />
          <span>Gia sư Tiếng Anh trí tuệ nhân tạo</span>
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-slate-900 md:text-4xl">Chatbot ViEng</h1>
        <p className="text-slate-500 max-w-lg mx-auto text-sm md:text-base">
          Hỏi bất kỳ điều gì về TOEIC/IELTS, upload tài liệu PDF hoặc hình ảnh đề thi để nhận câu trả lời tức thì.
        </p>
      </div>

      {/* Main chat box */}
      <div className="rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-100 overflow-hidden flex flex-col h-[600px]">
        {/* Header toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 bg-slate-50/50 px-6 py-3.5">
          <div className="flex items-center gap-2">
            <div className="h-3 w-3 rounded-full bg-green-500 animate-ping" />
            <span className="text-sm font-bold text-slate-700">Thầy cô AI ViEng</span>
          </div>
          <div className="flex items-center gap-3">
            {localStorage.getItem("vieng_access_token") && messages.length > 0 && (
              <button
                onClick={handleClearHistory}
                disabled={loading}
                title="Xóa lịch sử chat"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-rose-600 hover:text-rose-700 hover:bg-rose-50 transition-all px-2.5 py-1.5 rounded-xl border border-rose-100 bg-white cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
              >
                <Trash2 size={13} />
                <span>Xóa lịch sử</span>
              </button>
            )}
            <LlmProviderSelect value={llmProvider} onChange={setLlmProvider} />
          </div>
        </div>

        {/* Message Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/30">
          {messages.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center text-center max-w-md mx-auto space-y-4">
              <div className="rounded-2xl bg-indigo-50 p-4 text-indigo-600 animate-float">
                <MessageCircle size={36} />
              </div>
              <div className="space-y-1">
                <p className="text-base font-bold text-slate-800">Bắt đầu thảo luận kiến thức</p>
                <p className="text-sm text-slate-500">
                  Hãy gõ câu hỏi ngữ pháp hoặc bấm <Paperclip size={12} className="inline mx-0.5" /> để gửi ảnh chụp đề thi để AI dịch và giải thích chuyên sâu.
                </p>
              </div>
              
              {/* Prompt Suggestions */}
              <div className="w-full pt-4 grid grid-cols-1 gap-2">
                {SUGGESTIONS.map((item, idx) => (
                  <button
                    key={idx}
                    onClick={() => sendSuggestedMessage(item)}
                    className="w-full text-left rounded-xl border border-slate-200 bg-white hover:border-indigo-500 hover:bg-indigo-50/20 px-4 py-3 text-xs font-semibold text-slate-700 transition-all cursor-pointer shadow-sm"
                  >
                    💡 {item}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message List */}
          {messages.map((m, i) => {
            const isUser = m.role === "user";
            return (
              <div
                key={i}
                className={`flex gap-3 items-start animate-fade-in-up ${isUser ? "justify-end" : "justify-start"}`}
              >
                {/* AI Avatar */}
                {!isUser && (
                  <div className="h-9 w-9 rounded-full bg-indigo-600 text-white flex items-center justify-center shadow-md shrink-0">
                    <Bot size={18} />
                  </div>
                )}

                <div
                  className={`max-w-[75%] rounded-3xl p-4 shadow-sm border ${
                    isUser
                      ? "bg-indigo-600 text-white border-indigo-700"
                      : "bg-white text-slate-800 border-slate-100"
                  }`}
                >
                  {/* File Attachment Info */}
                  {m.attachment && (
                    <div className="mb-3 flex items-center gap-3 rounded-2xl bg-slate-100/10 p-3 border border-white/10">
                      {m.attachment.preview ? (
                        <img
                          src={m.attachment.preview}
                          alt={m.attachment.name}
                          className="h-14 w-14 rounded-xl object-cover shadow-sm"
                        />
                      ) : (
                        <div className="h-14 w-14 rounded-xl bg-white/20 flex items-center justify-center text-white/80 shadow-sm">
                          <FileText size={24} />
                        </div>
                      )}
                      <div className="text-xs space-y-0.5">
                        <div className="font-bold truncate max-w-[150px]">{m.attachment.name}</div>
                        <div className="opacity-80 text-[10px] uppercase font-bold">{m.attachment.type.split("/")[1] || "File"}</div>
                      </div>
                    </div>
                  )}

                  {/* Main text content */}
                  {m.content && (
                    <p className="whitespace-pre-wrap text-sm leading-relaxed font-semibold">{m.content}</p>
                  )}

                  {/* OCR Extractions */}
                  {m.extracted_text && (
                    <details className="mt-3 rounded-xl bg-slate-50 border border-slate-200/60 p-3 text-slate-700">
                      <summary className="cursor-pointer text-xs font-bold text-slate-600 select-none">
                        Nhấp để xem văn bản nhận diện (OCR)
                      </summary>
                      <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-[11px] font-mono leading-relaxed bg-white border border-slate-100 p-2.5 rounded-lg text-slate-600">
                        {m.extracted_text}
                      </pre>
                    </details>
                  )}

                  {/* RAG Citations */}
                  {m.sources?.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-100/60 flex flex-wrap gap-1.5 items-center">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mr-1">Tài liệu tham khảo:</span>
                      {m.sources.map((s, j) => (
                        <span
                          key={j}
                          className="inline-flex items-center gap-1 rounded-lg bg-indigo-50 border border-indigo-100/40 px-2.5 py-1 text-[11px] font-bold text-indigo-700 shadow-sm"
                        >
                          <BookOpen size={10} /> {s}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* User Avatar */}
                {isUser && (
                  <div className="h-9 w-9 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center shadow shrink-0 font-bold text-xs uppercase">
                    <User size={16} />
                  </div>
                )}
              </div>
            );
          })}

          {/* Loading status (Skeleton) */}
          {loading && (
            <div className="flex gap-3 items-start animate-pulse">
              <div className="h-9 w-9 rounded-full bg-slate-200 flex items-center justify-center shrink-0">
                <Bot size={18} className="text-slate-400" />
              </div>
              <div className="max-w-[75%] rounded-3xl p-4 bg-white border border-slate-100 shadow-sm space-y-2.5 min-w-[200px]">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-400">
                  <Loader2 size={13} className="animate-spin text-indigo-600" />
                  <span>AI đang tư duy...</span>
                </div>
                <div className="h-3 w-4/5 bg-slate-200 rounded-full" />
                <div className="h-3 w-3/5 bg-slate-200 rounded-full" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Error panel */}
        {error && (
          <div className="mx-6 mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-medium text-red-700 animate-fade-in-up">
            ⚠️ {error}
          </div>
        )}

        {/* Attachment preview bar */}
        {attachedFile && (
          <div className="mx-6 mb-3 flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-2.5 shadow-sm animate-fade-in-up">
            {previewUrl ? (
              <img
                src={previewUrl}
                alt={attachedFile.name}
                className="h-12 w-12 rounded-lg object-cover shadow-sm"
              />
            ) : (
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 shadow-sm">
                {attachedFile.type === "application/pdf" ? (
                  <FileText size={22} />
                ) : (
                  <ImageIcon size={22} />
                )}
              </div>
            )}
            <div className="flex-1 text-xs min-w-0">
              <div className="font-bold text-slate-800 truncate">{attachedFile.name}</div>
              <div className="text-slate-400 font-semibold mt-0.5">
                {(attachedFile.size / 1024).toFixed(1)} KB · Hệ thống sẽ OCR tự động
              </div>
            </div>
            <button
              onClick={clearAttachment}
              className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors cursor-pointer"
              title="Loại bỏ tệp"
              type="button"
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Input Bar */}
        <div className="border-t border-slate-100 p-4 bg-white">
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
              title="Đính kèm tài liệu học tập (ảnh/PDF)"
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 hover:border-indigo-200 transition-all disabled:opacity-50 cursor-pointer"
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
                  ? "Đặt câu hỏi về tài liệu này... (hoặc bỏ trống)"
                  : "Hỏi đáp ngữ pháp, từ vựng hoặc cấu trúc câu..."
              }
              className="flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100 transition-all text-slate-800 placeholder-slate-400 font-semibold"
              disabled={loading}
            />
            
            <button
              onClick={handleSend}
              disabled={loading || (!input.trim() && !attachedFile)}
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20 transition-all hover:scale-[1.03] active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
            >
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
