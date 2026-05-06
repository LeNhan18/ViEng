import axios from "axios";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 60000,
});

function getToken() {
  return localStorage.getItem("vieng_access_token");
}

export function setToken(token) {
  if (!token) localStorage.removeItem("vieng_access_token");
  else localStorage.setItem("vieng_access_token", token);
}

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export async function register({ email, password }) {
  const { data } = await api.post("/auth/register", { email, password });
  setToken(data.access_token);
  return data;
}

export async function login({ email, password }) {
  const { data } = await api.post("/auth/login", { email, password });
  setToken(data.access_token);
  return data;
}

export async function getMe() {
  const { data } = await api.get("/auth/me");
  return data;
}

export async function generateTest({ examType, skill, level, numQuestions, part }) {
  const body = {
    exam_type: examType,
    skill,
    level,
    num_questions: numQuestions,
  };
  if (part) body.part = part;
  if (arguments[0]?.llmProvider) body.llm_provider = arguments[0].llmProvider;
  const { data } = await api.post("/test/generate", body);
  return data;
}

export async function submitAnswers({ examType, skill, answers, part }) {
  const body = {
    exam_type: examType,
    skill,
    answers,
  };
  if (part) body.part = part;
  const { data } = await api.post("/test/submit", body);
  return data;
}

export async function searchKnowledge(query) {
  const { data } = await api.post(`/rag/search?query=${encodeURIComponent(query)}`);
  return data;
}

export async function translateText({ text, direction, level, useRag }) {
  const { data } = await api.post("/translate", {
    text,
    direction,
    level,
    use_rag: useRag,
    llm_provider: arguments[0]?.llmProvider || undefined,
  });
  return data;
}

/** Lấy URL audio phát âm tiếng Anh (TTS). Trả về blob URL để dùng với <audio src>. */
export async function getTtsAudioUrl(text) {
  const { data } = await api.post("/tts", { text }, { responseType: "blob" });
  return URL.createObjectURL(data);
}

export async function chat({ message, history }) {
  const { data } = await api.post("/chat", {
    message,
    history: history || [],
    llm_provider: arguments[0]?.llmProvider || undefined,
  });
  return data;
}

/**
 * Gửi ảnh hoặc PDF kèm câu hỏi: backend OCR -> RAG -> LLM trả lời.
 * Trả về { message, sources, extracted_text, file_name }.
 */
export async function chatWithOcr({ message, file, llmProvider }) {
  const form = new FormData();
  form.append("file", file);
  if (message) form.append("message", message);
  if (llmProvider) form.append("llm_provider", llmProvider);
  const { data } = await api.post("/chat/ocr", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  });
  return data;
}
