import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Creators from "./pages/Creators";
import CreatorDetail from "./pages/CreatorDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/creators" element={<Creators />} />
      <Route path="/creators/:id" element={<CreatorDetail />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
