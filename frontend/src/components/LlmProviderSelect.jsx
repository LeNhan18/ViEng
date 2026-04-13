const OPTIONS = [
  { value: "groq", label: "Groq (Llama 3.3 70B)" },
  { value: "openai", label: "OpenAI (GPT-4o-mini)" },
  { value: "hf_inference", label: "Fine-tuned (Hugging Face)" },
];

export default function LlmProviderSelect({ value, onChange }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-medium text-slate-500">Model:</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200"
      >
        {OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

