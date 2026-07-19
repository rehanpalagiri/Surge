import { ProfileCard, ChangeUsernameCard, ChangePasswordCard, ForgotPasswordCard, LogOutCard } from "../_components";

export default function AccountSettingsPage() {
  return (
    <>
      <ProfileCard />
      <ChangeUsernameCard />
      <ChangePasswordCard />
      <ForgotPasswordCard />
      <LogOutCard />
    </>
  );
}
