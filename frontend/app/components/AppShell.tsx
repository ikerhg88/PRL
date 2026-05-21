"use client";

import {
  Building2,
  Bell,
  FileText,
  LogIn,
  Network,
  UsersRound,
  UserPlus
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { clearSelectedCompany, readAuthSession, readSelectedCompany } from "../../lib/authClient";
import { ApiStatus } from "./ApiStatus";

type NavItem = {
  href: string;
  label: string;
  icon: typeof Network;
};

const navItems: NavItem[] = [
  { href: "/platforms", label: "Plataformas", icon: Network },
  { href: "/assign-worker", label: "Anadir trabajador", icon: UserPlus },
  { href: "/notifications", label: "Notificaciones", icon: Bell }
];

const armNavItems: NavItem[] = [
  { href: "/arm", label: "Empresa y trabajadores", icon: UsersRound }
];

const publicRoutes = ["/login", "/select-company", "/verify-email", "/auth/google/callback", "/onboarding/company"];

function isPublicRoute(pathname: string) {
  return publicRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

function isActive(pathname: string, href: string) {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "/";
  const [isSessionChecked, setIsSessionChecked] = useState(false);
  const [selectedCompanyName, setSelectedCompanyName] = useState("");

  useEffect(() => {
    if (isPublicRoute(pathname)) {
      setIsSessionChecked(true);
      return;
    }
    const session = readAuthSession();
    if (!session) {
      window.location.href = "/login";
      return;
    }
    const selectedCompany = readSelectedCompany();
    const selectedCompanyIsAllowed =
      selectedCompany && session.company_access.some((company) => company.company_id === selectedCompany.company_id);
    if (!selectedCompanyIsAllowed) {
      clearSelectedCompany();
      const nextPath = `${window.location.pathname}${window.location.search}`;
      window.location.href = `/select-company?next=${encodeURIComponent(nextPath)}`;
      return;
    }
    setSelectedCompanyName(selectedCompany.company_name);
    setIsSessionChecked(true);
  }, [pathname]);

  if (isPublicRoute(pathname)) {
    return children;
  }

  if (!isSessionChecked) {
    return <div className="contentArea" />;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebarHeader">
          <div>
            <p className="eyebrow">IPRL/CAE</p>
            <h1>Centro de plataformas</h1>
          </div>
          <ApiStatus />
        </div>
        {selectedCompanyName ? (
          <div className="selectedCompanyPill" aria-label="Empresa seleccionada">
            <Building2 aria-hidden="true" size={16} />
            <span>{selectedCompanyName}</span>
          </div>
        ) : null}

        <nav className="mainNav" aria-label="Navegacion principal">
          <div className="navGroup">
            <p className="navGroupTitle">ARM</p>
            {armNavItems.map((item) => {
              const Icon = item.icon;
              const active = isActive(pathname, item.href);
              return (
                <Link className={`navItem ${active ? "active" : ""}`} href={{ pathname: item.href }} aria-current={active ? "page" : undefined} key={item.href}>
                  <Icon aria-hidden="true" size={18} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
          <div className="navGroup">
            <p className="navGroupTitle">Operativa</p>
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isActive(pathname, item.href);
              return (
                <Link className={`navItem ${active ? "active" : ""}`} href={{ pathname: item.href }} aria-current={active ? "page" : undefined} key={item.href}>
                  <Icon aria-hidden="true" size={18} />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        <div className="quickNav" aria-label="Politica operativa">
          <p className="navGroupTitle">Reglas</p>
          <p className="smallText">
            <FileText aria-hidden="true" size={14} />
            ARM contiene solo datos propios de empresa, trabajadores y evidencias internas.
          </p>
          <p className="smallText">Las plataformas desactivadas no se revisan y no alimentan avisos operativos.</p>
          <p className="smallText">Las escrituras se preparan con aprobacion y lectura posterior.</p>
        </div>

        <Link className="navItem loginItem" href={{ pathname: "/login" }}>
          <LogIn aria-hidden="true" size={18} />
          <span>Login</span>
        </Link>
      </aside>

      <div className="contentArea">{children}</div>
    </div>
  );
}
