import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { getBootstrap } from "@/lib/bootstrap";
import { ChecklistPage } from "@/pages/ChecklistPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { Phase2Page } from "@/pages/Phase2Page";
import { ResumeImportsPage } from "@/pages/ResumeImportsPage";
import { SearchPage } from "@/pages/SearchPage";
import { TasksPage } from "@/pages/TasksPage";
import { UsersPage } from "@/pages/UsersPage";
import { WorkbenchPage } from "@/pages/WorkbenchPage";

function AppRoutes() {
  const bootstrap = getBootstrap();

  return (
    <Routes>
      <Route path="/" element={<Navigate to={bootstrap.username ? "/hr/tasks" : "/login"} replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/hr/tasks" element={<TasksPage />} />
      <Route path="/hr/search" element={<SearchPage />} />
      <Route path="/hr/workbench" element={<WorkbenchPage />} />
      <Route path="/hr/checklist" element={<ChecklistPage />} />
      <Route path="/hr/phase2" element={<Phase2Page />} />
      <Route path="/hr/resume-imports" element={<ResumeImportsPage />} />
      <Route path="/hr/users" element={<UsersPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
