import { Route, Routes } from "react-router-dom";
import { TopBar } from "./ui/TopBar";
import { Investigations } from "./screens/Investigations";
import { InvestigationRoute, Page } from "./screens/InvestigationRoute";
import { NewInvestigation } from "./screens/NewInvestigation";
import { Settings } from "./screens/Settings";
import { Banner } from "./ui/Banner";

export function App() {
  return (
    <div className="ng-app">
      <TopBar />
      <Routes>
        <Route path="/" element={<Investigations />} />
        <Route path="/new" element={<NewInvestigation />} />
        <Route path="/investigations/:id" element={<InvestigationRoute />} />
        <Route path="/investigations/:id/board" element={<InvestigationRoute board />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Page><Banner title="No such page." /></Page>} />
      </Routes>
    </div>
  );
}

