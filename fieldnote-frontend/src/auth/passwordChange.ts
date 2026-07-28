export interface ChangePasswordResponse {
  must_change_password: boolean;
}

export type ApiRequester = <T>(path: string, options?: RequestInit) => Promise<T>;

export async function changeInitialPassword(
  password: string,
  request: ApiRequester,
  refreshProfile: () => Promise<void>,
): Promise<void> {
  const response = await request<ChangePasswordResponse>("/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ password }),
  });
  if (response.must_change_password) {
    throw new Error("Zmiana hasła nie została potwierdzona przez usługę.");
  }
  await refreshProfile();
}
