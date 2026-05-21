export type AuthUser = {
  id: number;
  tenant_id: number;
  email: string;
  name: string;
  role_id: number | null;
  status: string;
};

export type AuthCompanyAccess = {
  company_id: number;
  company_name: string;
  company_type: string;
  access_level: string;
  permissions: string[];
};

export type AuthSession = {
  tenant_id: number;
  user: AuthUser;
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  company_access: AuthCompanyAccess[];
};

export const sessionStorageKey = "iprl_cae_session";
export const selectedCompanyStorageKey = "iprl_cae_selected_company";

export function readAuthSession(): AuthSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(sessionStorageKey);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(sessionStorageKey);
    return null;
  }
}

export function writeAuthSession(session: AuthSession) {
  window.localStorage.setItem(sessionStorageKey, JSON.stringify(session));
  const selectedCompany = readSelectedCompany();
  if (selectedCompany && !session.company_access.some((company) => company.company_id === selectedCompany.company_id)) {
    clearSelectedCompany();
  }
}

export function clearAuthSession() {
  window.localStorage.removeItem(sessionStorageKey);
  clearSelectedCompany();
}

export function readSelectedCompany(): AuthCompanyAccess | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(selectedCompanyStorageKey);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as AuthCompanyAccess;
  } catch {
    window.localStorage.removeItem(selectedCompanyStorageKey);
    return null;
  }
}

export function writeSelectedCompany(company: AuthCompanyAccess) {
  window.localStorage.setItem(selectedCompanyStorageKey, JSON.stringify(company));
}

export function clearSelectedCompany() {
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(selectedCompanyStorageKey);
  }
}
