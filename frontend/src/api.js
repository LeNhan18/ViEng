import axios from "axios";

const api = axios.create({
  baseURL: "/api/v1",
  timeout: 60000,
});

export async function generateTest({ examType, skill, level, numQuestions, part }) {
  const body = {
    exam_type: examType,
    skill,
    level,
    num_questions: numQuestions,
  };
  if (part) body.part = part;
  const { data } = await api.post("/test/generate", body);
  return data;
}

export async function submitAnswers({ examType, skill, answers }) {
  const { data } = await api.post("/test/submit", {
    exam_type: examType,
    skill,
    answers,
  });
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
  });
  return data;
}
