import { Outlet, Link, useLocation } from "react-router-dom";
import { BookOpen, Home, GraduationCap } from "lucide-react";

const navItems = [
  { path: "/", label: "Trang chủ", icon: Home },
  { path: "/exam", label: "Làm bài", icon: GraduationCap },
];

export default function Layout() {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-indigo-50">
      <header className="sticky top-0 z-50 border-b border-white/20 bg-white/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
              <BookOpen size={20} />
            </div>
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
