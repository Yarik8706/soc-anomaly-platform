import { LoginForm } from "@/features/auth/login-form";
import { safeReturnTo } from "@/features/auth/navigation";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ returnTo?: string }>;
}) {
  const { returnTo } = await searchParams;
  return <LoginForm returnTo={safeReturnTo(returnTo)} />;
}
