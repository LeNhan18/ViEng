import { useNavigate } from "react-router-dom";
import { BookOpen, Brain, Target, TrendingUp, ArrowRight, Languages, MessageSquare, Sparkles } from "lucide-react";

const features = [
  {
    icon: Brain,
    title: "AI tạo đề cá nhân hóa",
    desc: "Đề thi được sinh ra độc bản theo đúng trình độ và kỹ năng bạn lựa chọn.",
    color: "bg-purple-500/10 text-purple-600 border-purple-500/20",
    glow: "shadow-purple-500/5",
  },
  {
    icon: Target,
    title: "Giải thích chuẩn sư phạm",
    desc: "Feedback dễ hiểu, dí dỏm chuẩn phong cách thầy cô Việt Nam, bám sát đề thi.",
    color: "bg-blue-500/10 text-blue-600 border-blue-500/20",
    glow: "shadow-blue-500/5",
  },
  {
    icon: BookOpen,
    title: "Trích dẫn nguồn RAG uy tín",
    desc: "Được đối chiếu trực tiếp từ thư viện sách ngữ pháp chính thống để đảm bảo độ chính xác.",
    color: "bg-emerald-500/10 text-emerald-600 border-emerald-500/20",
    glow: "shadow-emerald-500/5",
  },
  {
    icon: TrendingUp,
    title: "Phân tích điểm yếu tự động",
    desc: "Theo dõi lịch sử làm bài, nhận diện lỗ hổng kiến thức để cải thiện điểm số.",
    color: "bg-amber-500/10 text-amber-600 border-amber-500/20",
    glow: "shadow-amber-500/5",
  },
];

const tags = [
  { label: "TOEIC Reading", state: { examType: "toeic", skill: "reading", part: "part5" } },
  { label: "TOEIC Listening", state: { examType: "toeic", skill: "listening" } },
  { label: "IELTS Reading", state: { examType: "ielts", skill: "reading" } },
  { label: "IELTS Writing", state: { examType: "ielts", skill: "writing" } },
  { label: "IELTS Speaking", state: { examType: "ielts", skill: "speaking" } },
];

export default function Home() {
  const navigate = useNavigate();

  const handleQuickNav = (path, state = {}) => {
    navigate(path, { state });
  };

  return (
    <div className="space-y-16 py-4">
      {/* Hero Section */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-indigo-950 to-purple-950 px-6 py-16 text-center text-white shadow-2xl md:px-16 md:py-24">
        {/* Glow ambient effects */}
        <div className="absolute top-0 left-1/4 h-80 w-80 rounded-full bg-indigo-500/10 blur-[120px] animate-pulse-glow" />
        <div className="absolute bottom-0 right-1/4 h-96 w-96 rounded-full bg-purple-500/10 blur-[150px] animate-pulse-glow" />
        
        {/* Grid pattern overlay */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:32px_32px] opacity-40" />

        <div className="relative z-10 space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-xs font-semibold text-indigo-300">
            <Sparkles size={12} className="animate-spin" />
            <span>Nền tảng luyện thi tiếng Anh đột phá bằng AI</span>
          </div>

          <h1 className="text-4xl font-extrabold leading-tight tracking-tight md:text-6xl max-w-4xl mx-auto">
            Bứt phá điểm TOEIC/IELTS
            <br />
            <span className="bg-gradient-to-r from-amber-300 via-orange-300 to-amber-200 bg-clip-text text-transparent">
              Cùng Trợ Lý Thầy Cô AI
            </span>
          </h1>

          <p className="mx-auto max-w-2xl text-base md:text-lg text-slate-300 font-medium leading-relaxed">
            Nhận đề thi biên soạn riêng biệt, giải đáp siêu chi tiết, trích dẫn chuẩn xác từ tài liệu chính thống. Tất cả hoàn toàn miễn phí dành cho sinh viên Việt Nam.
          </p>

          <div className="flex flex-wrap justify-center gap-4 pt-4">
            <button
              onClick={() => handleQuickNav("/exam")}
              className="group inline-flex items-center gap-2 rounded-2xl bg-indigo-600 hover:bg-indigo-500 px-8 py-4 text-base font-bold text-white shadow-xl shadow-indigo-600/30 transition-all duration-200 hover:scale-[1.03] active:scale-95 cursor-pointer"
            >
              Luyện đề thi ngay
              <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
            </button>
            <button
              onClick={() => handleQuickNav("/chat")}
              className="inline-flex items-center gap-2 rounded-2xl bg-white/10 hover:bg-white/15 px-8 py-4 text-base font-bold text-white border border-white/10 transition-all duration-200 hover:scale-[1.03] active:scale-95 cursor-pointer"
            >
              <MessageSquare size={18} />
              Hỏi đáp ngữ pháp
            </button>
          </div>
        </div>
      </section>

      {/* Quick Access Cards */}
      <section className="grid gap-6 md:grid-cols-3">
        <div
          onClick={() => handleQuickNav("/exam")}
          className="group relative rounded-2xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer flex flex-col justify-between"
        >
          <div>
            <div className="mb-4 inline-flex rounded-xl bg-indigo-50 p-3 text-indigo-600 group-hover:scale-110 transition-transform">
              <Brain size={24} />
            </div>
            <h3 className="mb-2 text-lg font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">AI Test Generator</h3>
            <p className="text-sm leading-relaxed text-slate-500">Tạo đề thi TOEIC/IELTS theo sở thích và năng lực. Hỗ trợ đủ các phần thi phổ biến.</p>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-xs font-bold text-indigo-600">
            <span>Bắt đầu làm bài</span>
            <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        <div
          onClick={() => handleQuickNav("/chat")}
          className="group relative rounded-2xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer flex flex-col justify-between"
        >
          <div>
            <div className="mb-4 inline-flex rounded-xl bg-purple-50 p-3 text-purple-600 group-hover:scale-110 transition-transform">
              <MessageSquare size={24} />
            </div>
            <h3 className="mb-2 text-lg font-bold text-slate-900 group-hover:text-purple-600 transition-colors">AI Chatbot Sư Phạm</h3>
            <p className="text-sm leading-relaxed text-slate-500">Hỏi đáp lỗi sai tiếng Anh, tải file PDF đề thi hoặc chụp hình bài tập để AI dịch và giải thích.</p>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-xs font-bold text-purple-600">
            <span>Trò chuyện ngay</span>
            <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
          </div>
        </div>

        <div
          onClick={() => handleQuickNav("/translate")}
          className="group relative rounded-2xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-xl transition-all duration-300 hover:-translate-y-1 cursor-pointer flex flex-col justify-between"
        >
          <div>
            <div className="mb-4 inline-flex rounded-xl bg-emerald-50 p-3 text-emerald-600 group-hover:scale-110 transition-transform">
              <Languages size={24} />
            </div>
            <h3 className="mb-2 text-lg font-bold text-slate-900 group-hover:text-emerald-600 transition-colors">AI Translator</h3>
            <p className="text-sm leading-relaxed text-slate-500">Dịch thuật Anh - Việt đa cấp độ, cung cấp bảng phân tích từ vựng quan trọng và ngữ pháp chính.</p>
          </div>
          <div className="mt-4 flex items-center gap-1.5 text-xs font-bold text-emerald-600">
            <span>Dịch văn bản</span>
            <ArrowRight size={14} className="group-hover:translate-x-1 transition-transform" />
          </div>
        </div>
      </section>

      {/* Features Showcase */}
      <section className="space-y-8">
        <div className="text-center space-y-2">
          <h2 className="text-3xl font-extrabold text-slate-900">Tại sao nên học với ViEng?</h2>
          <p className="text-slate-500 max-w-xl mx-auto">Chúng tôi ứng dụng công nghệ trí tuệ nhân tạo thế hệ mới mang tới trải nghiệm tối ưu nhất.</p>
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          {features.map(({ icon: Icon, title, desc, color, glow }) => (
            <div
              key={title}
              className={`group rounded-2xl border border-slate-100 bg-white p-6 shadow-sm transition-all duration-300 hover:shadow-md hover:border-slate-200 flex gap-4 ${glow}`}
            >
              <div className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border ${color} transition-transform duration-200 group-hover:scale-105`}>
                <Icon size={22} />
              </div>
              <div className="space-y-1">
                <h3 className="text-base font-bold text-slate-900">{title}</h3>
                <p className="text-sm leading-relaxed text-slate-500">{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Exam Categories Navigation */}
      <section className="rounded-3xl border border-slate-200/80 bg-white/70 backdrop-blur-sm p-8 text-center shadow-sm relative overflow-hidden">
        <div className="absolute top-0 right-0 h-32 w-32 rounded-full bg-indigo-500/5 blur-3xl" />
        <div className="relative z-10 max-w-2xl mx-auto space-y-6">
          <div className="space-y-2">
            <h2 className="text-2xl font-bold text-slate-900">Bắt đầu học theo kỹ năng</h2>
            <p className="text-sm text-slate-500">Chọn nhanh một kỹ năng bên dưới để AI chuẩn bị đề thi ngay lập tức.</p>
          </div>
          
          <div className="flex flex-wrap justify-center gap-3">
            {tags.map(({ label, state }) => (
              <button
                key={label}
                onClick={() => handleQuickNav("/exam", state)}
                className="rounded-full bg-indigo-50 hover:bg-indigo-100/80 active:scale-95 border border-indigo-100 px-5 py-2 text-sm font-semibold text-indigo-700 transition-all cursor-pointer shadow-sm shadow-indigo-100/10 hover:shadow-md"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
