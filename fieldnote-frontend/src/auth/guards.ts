export type FieldnoteRole = "viewer" | "analyst" | "admin";

export interface AuthIdentity {
  role: FieldnoteRole;
  mustChangePassword: boolean;
}

export type AuthScreen = "loading" | "login" | "change-password" | "app" | "configuration-error";

export function screenForAuth(
  state: "loading" | "configured" | "configuration-error",
  identity: AuthIdentity | null,
): AuthScreen {
  if (state === "loading") return "loading";
  if (state === "configuration-error") return "configuration-error";
  if (!identity) return "login";
  return identity.mustChangePassword ? "change-password" : "app";
}

export function canAccessAdminUsers(identity: AuthIdentity | null): boolean {
  return identity?.role === "admin" && !identity.mustChangePassword;
}

export function canWriteData(identity: AuthIdentity | null): boolean {
  return (identity?.role === "analyst" || identity?.role === "admin") && !identity.mustChangePassword;
}
