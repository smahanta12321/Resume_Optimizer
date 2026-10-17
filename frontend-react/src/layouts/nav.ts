import {
  Briefcase,
  ClipboardList,
  FileText,
  Layers,
  LayoutDashboard,
  Settings,
  Tags,
  UserRound,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

/** Only screens backed by real API routes appear here. */
export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/profile", label: "Master Profile", icon: UserRound },
  { to: "/skills", label: "Skills Library", icon: Tags },
  { to: "/roles", label: "Role Profiles", icon: Layers },
  { to: "/jobs", label: "Job Descriptions", icon: Briefcase },
  { to: "/resumes", label: "Resume Versions", icon: FileText },
  { to: "/tracker", label: "Application Tracker", icon: ClipboardList },
  { to: "/settings", label: "Settings", icon: Settings },
];
