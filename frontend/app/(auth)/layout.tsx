import { Logo } from "@/components/layout/logo";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-sidebar p-10 lg:flex">
        <Logo />
        <blockquote className="space-y-2">
          <p className="text-lg">
            “Payments land in our own bank account the same minute, and the receptionist just verifies the UTR.”
          </p>
          <footer className="text-sm text-muted-foreground">Clinic owner, early design partner</footer>
        </blockquote>
      </div>
      <div className="flex items-center justify-center p-6">{children}</div>
    </div>
  );
}
