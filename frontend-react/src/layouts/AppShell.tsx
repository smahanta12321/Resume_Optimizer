import { FilePlus2, FileText, Menu, Monitor, Moon, PanelLeftClose, PanelLeftOpen, Sun } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import { NAV } from "./nav";

const COLLAPSE_KEY = "ro-sidebar-collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

function NavLinks({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          title={collapsed ? label : undefined}
          aria-label={collapsed ? label : undefined}
          className={({ isActive }) =>
            cn(
              "flex h-9 items-center gap-3 rounded-md px-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-surface-muted hover:text-foreground",
              isActive && "bg-primary-soft text-primary hover:bg-primary-soft hover:text-primary",
              collapsed && "justify-center px-0",
            )
          }
        >
          <Icon className="size-4 shrink-0" aria-hidden />
          {!collapsed && <span className="truncate">{label}</span>}
        </NavLink>
      ))}
    </nav>
  );
}

function Brand({ collapsed }: { collapsed?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight" aria-label="Resume Optimizer home">
      <span className="grid size-7 place-items-center rounded-md bg-primary text-primary-foreground">
        <FileText className="size-4" aria-hidden />
      </span>
      {!collapsed && <span>Resume Optimizer</span>}
    </Link>
  );
}

function TailorButton({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  return (
    <Button asChild size={collapsed ? "icon" : "md"} className={cn(!collapsed && "w-full justify-start")}>
      <Link to="/tailor" onClick={onNavigate} title={collapsed ? "Tailor a resume" : undefined} aria-label="Tailor a resume">
        <FilePlus2 />
        {!collapsed && "Tailor a resume"}
      </Link>
    </Button>
  );
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  return (
    <Button variant="ghost" size="icon-sm" onClick={() => setTheme(next)} aria-label={`Theme: ${theme}. Switch to ${next}.`} title={`Theme: ${theme}`}>
      <Icon />
    </Button>
  );
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { pathname } = useLocation();

  const toggle = () => {
    setCollapsed((c) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, c ? "0" : "1");
      } catch {
        // not persisted
      }
      return !c;
    });
  };

  return (
    <div className="flex min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:shadow">
        Skip to content
      </a>

      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col gap-4 border-r bg-surface px-3 py-4 transition-[width] duration-200 lg:flex",
          collapsed ? "w-16 items-center" : "w-60",
        )}
      >
        <div className={cn("flex items-center", collapsed ? "justify-center" : "justify-between px-1")}>
          <Brand collapsed={collapsed} />
        </div>
        <TailorButton collapsed={collapsed} />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <NavLinks collapsed={collapsed} />
        </div>
        <div className={cn("flex items-center gap-1", collapsed ? "flex-col" : "justify-between")}>
          <ThemeToggle />
          <Button variant="ghost" size="icon-sm" onClick={toggle} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed}>
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-surface/90 px-4 backdrop-blur lg:hidden">
          <Button variant="ghost" size="icon-sm" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
            <Menu />
          </Button>
          <Brand />
          <div className="ml-auto">
            <ThemeToggle />
          </div>
        </header>

        <Dialog open={mobileOpen} onOpenChange={setMobileOpen}>
          <DialogContent title="Navigation" variant="sheet-left">
            <div className="flex flex-col gap-4">
              <TailorButton onNavigate={() => setMobileOpen(false)} />
              <NavLinks onNavigate={() => setMobileOpen(false)} />
            </div>
          </DialogContent>
        </Dialog>

        <main id="main" key={pathname} className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 animate-in sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
