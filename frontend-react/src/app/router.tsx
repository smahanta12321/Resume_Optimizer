import { createBrowserRouter, type RouteObject } from "react-router";
import { AppShell } from "@/layouts/AppShell";
import { RouteError } from "./RouteError";
import { NotFound } from "./NotFound";

// Each screen is its own chunk, loaded on first visit.
export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    errorElement: <RouteError />,
    children: [
      { index: true, lazy: async () => ({ Component: (await import("@/features/dashboard/DashboardPage")).DashboardPage }) },
      { path: "profile", lazy: async () => ({ Component: (await import("@/features/profile/ProfilePage")).ProfilePage }) },
      { path: "skills", lazy: async () => ({ Component: (await import("@/features/skills/SkillsPage")).SkillsPage }) },
      { path: "roles", lazy: async () => ({ Component: (await import("@/features/roles/RolesPage")).RolesPage }) },
      { path: "jobs", lazy: async () => ({ Component: (await import("@/features/jobs/JobsPage")).JobsPage }) },
      { path: "jobs/new", lazy: async () => ({ Component: (await import("@/features/jobs/JobImportPage")).JobImportPage }) },
      { path: "jobs/:jobId", lazy: async () => ({ Component: (await import("@/features/jobs/JobDetailPage")).JobDetailPage }) },
      { path: "tailor", lazy: async () => ({ Component: (await import("@/features/resumes/TailorStartPage")).TailorStartPage }) },
      { path: "jobs/:jobId/tailor", lazy: async () => ({ Component: (await import("@/features/resumes/TailorPage")).TailorPage }) },
      { path: "resumes", lazy: async () => ({ Component: (await import("@/features/resumes/ResumesPage")).ResumesPage }) },
      { path: "resumes/:versionId", lazy: async () => ({ Component: (await import("@/features/resumes/ResumeVersionPage")).ResumeVersionPage }) },
      { path: "tracker", lazy: async () => ({ Component: (await import("@/features/tracker/TrackerPage")).TrackerPage }) },
      { path: "settings", lazy: async () => ({ Component: (await import("@/features/settings/SettingsPage")).SettingsPage }) },
      { path: "*", element: <NotFound /> },
    ],
  },
];

export const createRouter = () => createBrowserRouter(routes);
