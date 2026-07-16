import { Route, Routes } from "react-router-dom";
import { Landing } from "./pages/Landing.js";
import { Login } from "./pages/Login.js";

export function App(): React.ReactElement {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
    </Routes>
  );
}
