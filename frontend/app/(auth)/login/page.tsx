import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Sign in</CardTitle>
        <CardDescription>Mobile OTP, email and password, and Google sign-in are wired up in Phase 2.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="mobile">Mobile number</Label>
          <Input id="mobile" inputMode="tel" placeholder="+91 98765 43210" disabled />
        </div>
        <Button className="w-full" disabled>
          Send OTP
        </Button>
      </CardContent>
    </Card>
  );
}
