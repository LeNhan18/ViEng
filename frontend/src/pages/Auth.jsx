import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { login, register } from "../api";

export default function Auth() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const mode = useMemo(() => (params.get("mode") === "register" ? "register" : "login"), [params]);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "register") await register({ email, password });
      else await login({ email, password });
      navigate("/");
    } catch (err) {
      setError(err?.response?.data?.detail || "Không thể đăng nhập/đăng ký. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md">
      <div className="rounded-2xl border border-white/30 bg-white/70 p-6 shadow-xl shadow-indigo-100 backdrop-blur">
        <h1 className="text-2xl font-bold text-slate-900">
          {mode === "register" ? "Tạo tài khoản" : "Đăng nhập"}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {mode === "register"
            ? "Tạo tài khoản để lưu tiến trình và cá nhân hoá."
            : "Đăng nhập để tiếp tục học tập."}
        </p>

        <form className="mt-5 space-y-4" onSubmit={onSubmit}>
          <div>
            <label className="text-sm font-medium text-slate-700">Email</label>
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              required
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>

          <div>
            <label className="text-sm font-medium text-slate-700">Mật khẩu</label>
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
              required
              className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500"
              placeholder={mode === "register" ? "Tối thiểu 8 ký tự" : "Nhập mật khẩu"}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              minLength={mode === "register" ? 8 : 1}
            />
          </div>

          {error ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </div>
          ) : null}

          <button
            disabled={loading}
            className="w-full rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-md shadow-indigo-200 transition hover:bg-indigo-700 disabled:opacity-60"
          >
            {loading ? "Đang xử lý..." : mode === "register" ? "Đăng ký" : "Đăng nhập"}
          </button>
        </form>

        <div className="mt-4 text-sm text-slate-600">
          {mode === "register" ? (
            <a className="font-medium text-indigo-700 hover:underline" href="/auth?mode=login">
              Đã có tài khoản? Đăng nhập
            </a>
          ) : (
            <a className="font-medium text-indigo-700 hover:underline" href="/auth?mode=register">
              Chưa có tài khoản? Tạo tài khoản
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

