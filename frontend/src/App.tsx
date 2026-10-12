import { Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Creators from "./pages/Creators";
import CreatorDetail from "./pages/CreatorDetail";
import SeriesList from "./pages/SeriesList";
import SeriesDetail from "./pages/SeriesDetail";
import EpisodeDetail from "./pages/EpisodeDetail";
import Review from "./pages/Review";
import YouTube from "./pages/YouTube";
import Analytics from "./pages/Analytics";
import Experiments, { ExperimentDetail } from "./pages/Experiments";
import Audience from "./pages/Audience";

export default function App() {
  return (
    <Routes>
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/creators" element={<Creators />} />
      <Route path="/creators/:id" element={<CreatorDetail />} />
      <Route path="/series" element={<SeriesList />} />
      <Route path="/series/:id" element={<SeriesDetail />} />
      <Route path="/episodes/:id" element={<EpisodeDetail />} />
      <Route path="/review" element={<Review />} />
      <Route path="/youtube" element={<YouTube />} />
      <Route path="/analytics" element={<Analytics />} />
      <Route path="/experiments" element={<Experiments />} />
      <Route path="/experiments/:id" element={<ExperimentDetail />} />
      <Route path="/simulation" element={<Audience />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
