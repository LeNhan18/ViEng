import { Outlet, Link, useLocation } from "react-router-dom";
import { Home, GraduationCap, Languages, MessageCircle, LogIn, LogOut, User } from "lucide-react";
import { setToken, getMe } from "../api";
import { useEffect, useState } from "react";

const navItems = [
  { path: "/", label: "Trang chủ", icon: Home },
  { path: "/exam", label: "Làm bài", icon: GraduationCap },
  { path: "/chat", label: "Chatbot", icon: MessageCircle },
  { path: "/translate", label: "Dịch thuật", icon: Languages },
];

export default function Layout() {
  const { pathname } = useLocation();
  const [me, setMe] = useState(null);

  useEffect(() => {
    let mounted = true;
    getMe()
      .then((u) => {
        if (mounted) setMe(u);
      })
      .catch(() => {
        if (mounted) setMe(null);
      });
    return () => {
      mounted = false;
    };
  }, []);

  function logout() {
    setToken(null);
    setMe(null);
    window.location.href = "/";
  }

  return (
    <div className="min-h-screen bg-slate-50 bg-dot-grid flex flex-col">
      <header className="sticky top-0 z-50 glass-panel border-b border-slate-200/60 shadow-sm transition-all duration-300">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-3 group transition-transform duration-200 hover:scale-[1.02]">
            <div className="relative">
              <img src="/logoViEng.jpg" alt="ViEng" className="h-10 w-10 rounded-full object-cover shadow-md ring-2 ring-indigo-500/20" />
              <span className="absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-white bg-green-500" />
            </div>
            <span className="text-2xl font-black tracking-tight text-slate-900">
              Vi<span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">Eng</span>
            </span>
          </Link>

          <nav className="flex items-center gap-1.5">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all duration-200 active:scale-95 ${
                  pathname === path
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20 translate-y-[-1px]"
                    : "text-slate-600 hover:bg-indigo-50 hover:text-indigo-600"
                }`}
              >
                <Icon size={16} className={`${pathname === path ? "animate-pulse" : ""}`} />
                <span>{label}</span>
              </Link>
            ))}

            <div className="ml-3 h-6 w-px bg-slate-200" />

            {me ? (
              <button
                onClick={logout}
                className="flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold text-slate-600 transition-all duration-200 hover:bg-rose-50 hover:text-rose-600 active:scale-95 ml-2 cursor-pointer"
                title={me.email}
              >
                <div className="h-6 w-6 rounded-full bg-indigo-100 flex items-center justify-center text-xs text-indigo-700 font-bold">
                  {me.email.slice(0, 2).toUpperCase()}
                </div>
                <span className="max-w-[100px] truncate">{me.email.split("@")[0]}</span>
                <LogOut size={16} className="opacity-70" />
              </button>
            ) : (
              <Link
                to="/auth?mode=login"
                className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold transition-all duration-200 active:scale-95 ml-2 ${
                  pathname.startsWith("/auth")
                    ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/20"
                    : "bg-indigo-50 text-indigo-600 hover:bg-indigo-100"
                }`}
              >
                <LogIn size={16} />
                <span>Đăng nhập</span>
              </Link>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl w-full px-4 py-8 flex-1 animate-fade-in-up">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200/80 bg-white/60 py-6 text-center text-sm text-slate-500 backdrop-blur-sm">
        <div className="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="font-medium">ViEng — Trợ lý luyện thi tiếng Anh AI cho sinh viên Việt Nam</p>
          <div className="flex gap-4 text-xs font-semibold text-slate-400">
            <span className="hover:text-indigo-600 transition-colors cursor-pointer">Điều khoản</span>
            <span>·</span>
            <span className="hover:text-indigo-600 transition-colors cursor-pointer">Bảo mật</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
