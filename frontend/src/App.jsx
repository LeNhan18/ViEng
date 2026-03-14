import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Home from "./pages/Home";
import Exam from "./pages/Exam";
import Result from "./pages/Result";
import Translate from "./pages/Translate";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/exam" element={<Exam />} />
        <Route path="/result" element={<Result />} />
        <Route path="/translate" element={<Translate />} />
      </Route>
    </Routes>
  );
}
