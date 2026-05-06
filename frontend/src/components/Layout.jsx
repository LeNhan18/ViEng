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
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50">
      <header className="sticky top-0 z-50 border-b border-white/20 bg-white/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2.5">
            <img src="/logoViEng.jpg" alt="ViEng" className="h-9 w-9 rounded-full object-cover" />
            <span className="text-xl font-bold tracking-tight text-slate-900">
              Vi<span className="text-indigo-600">Eng</span>
            </span>
          </Link>

          <nav className="flex items-center gap-1">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
                  pathname === path
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-200"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <Icon size={16} />
                {label}
              </Link>
            ))}

            <div className="ml-2 h-6 w-px bg-slate-200" />

            {me ? (
              <button
                onClick={logout}
                className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition-all hover:bg-slate-100 hover:text-slate-900"
                title={me.email}
              >
                <User size={16} />
                {me.email.split("@")[0]}
                <LogOut size={16} />
              </button>
            ) : (
              <Link
                to="/auth?mode=login"
                className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all ${
                  pathname.startsWith("/auth")
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-200"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`}
              >
                <LogIn size={16} />
                Đăng nhập
              </Link>
            )}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-slate-200 bg-white/50 py-6 text-center text-sm text-slate-500">
        ViEng — Trợ lý luyện thi tiếng Anh AI cho sinh viên Việt Nam
      </footer>
    </div>
  );
}
