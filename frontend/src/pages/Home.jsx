import { useNavigate } from "react-router-dom";
import { BookOpen, Brain, Target, TrendingUp, ArrowRight } from "lucide-react";

const features = [
  {
    icon: Brain,
    title: "AI tạo đề cá nhân hóa",
    desc: "Đề thi được tạo bởi AI dựa trên trình độ và kỹ năng bạn chọn",
    color: "bg-purple-100 text-purple-600",
  },
  {
    icon: Target,
    title: "Giải thích chi tiết",
    desc: "Feedback theo phong cách thầy cô Việt Nam, dễ hiểu, gần gũi",
    color: "bg-blue-100 text-blue-600",
  },
  {
    icon: BookOpen,
    title: "Nguồn tài liệu uy tín",
    desc: "Trích dẫn grammar rules từ nguồn chính xác qua công nghệ RAG",
    color: "bg-green-100 text-green-600",
  },
  {
    icon: TrendingUp,
    title: "Theo dõi tiến độ",
    desc: "Phân tích điểm yếu và gợi ý bài tập phù hợp",
    color: "bg-orange-100 text-orange-600",
  },
];

export default function Home() {
  const navigate = useNavigate();

  return (
    <div className="space-y-16">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 via-indigo-700 to-purple-800 px-8 py-16 text-center text-white shadow-2xl shadow-indigo-200 md:px-16 md:py-24">
        <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iLjA1Ij48cGF0aCBkPSJNMzYgMzRoLTJ2LTRoMnYtMmg0djJoMnY0aC0ydjJoLTR2LTJ6bTAtMTZoLTJ2LTRoMlY4aDR2MmgydjRoLTJ2MmgtNHYtMnptMTYgMTZoLTJ2LTRoMnYtMmg0djJoMnY0aC0ydjJoLTR2LTJ6Ii8+PC9nPjwvZz48L3N2Zz4=')] opacity-30" />
        <div className="relative">
          <div className="mb-4 inline-block rounded-full bg-white/10 px-4 py-1.5 text-sm font-medium backdrop-blur">
            Powered by AI & RAG
          </div>
          <h1 className="mb-4 text-4xl font-extrabold leading-tight md:text-6xl">
            Luyện thi TOEIC/IELTS
            <br />
            <span className="bg-gradient-to-r from-amber-300 to-orange-300 bg-clip-text text-transparent">
              cùng AI thông minh
            </span>
          </h1>
          <p className="mx-auto mb-8 max-w-2xl text-lg text-indigo-100">
            Bài test cá nhân hóa, giải thích chi tiết theo phong cách thầy cô Việt, trích dẫn nguồn uy tín — tất cả miễn phí.
          </p>
          <button
            onClick={() => navigate("/exam")}
            className="group inline-flex items-center gap-2 rounded-2xl bg-white px-8 py-4 text-lg font-bold text-indigo-700 shadow-xl transition-all hover:scale-105 hover:shadow-2xl"
          >
            Bắt đầu làm bài
            <ArrowRight size={20} className="transition-transform group-hover:translate-x-1" />
          </button>
        </div>
      </section>

      <section>
        <h2 className="mb-8 text-center text-2xl font-bold text-slate-900">Tính năng nổi bật</h2>
        <div className="grid gap-6 sm:grid-cols-2">
          {features.map(({ icon: Icon, title, desc, color }) => (
            <div
              key={title}
              className="group rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition-all hover:-translate-y-1 hover:shadow-lg"
            >
              <div className={`mb-4 inline-flex rounded-xl p-3 ${color}`}>
                <Icon size={24} />
              </div>
              <h3 className="mb-2 text-lg font-semibold text-slate-900">{title}</h3>
              <p className="text-sm leading-relaxed text-slate-500">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h2 className="mb-2 text-xl font-bold text-slate-900">Hỗ trợ các kỳ thi</h2>
        <p className="mb-6 text-slate-500">Chọn kỳ thi và kỹ năng bạn muốn luyện</p>
        <div className="flex flex-wrap justify-center gap-3">
          {["TOEIC Reading", "TOEIC Listening", "IELTS Writing", "IELTS Reading", "IELTS Speaking"].map((tag) => (
            <span key={tag} className="rounded-full bg-indigo-50 px-4 py-2 text-sm font-medium text-indigo-700">
              {tag}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}
