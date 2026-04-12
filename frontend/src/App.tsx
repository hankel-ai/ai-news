import { useState } from "react";
import Layout from "./components/Layout";
import HeadlinesPage from "./pages/HeadlinesPage";
import SettingsPage from "./pages/SettingsPage";

type Tab = "headlines" | "settings";

export default function App() {
  const [tab, setTab] = useState<Tab>("headlines");

  return (
    <Layout activeTab={tab} onTabChange={setTab}>
      {tab === "headlines" ? <HeadlinesPage /> : <SettingsPage />}
    </Layout>
  );
}
