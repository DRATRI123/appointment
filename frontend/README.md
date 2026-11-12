# Frontend (Next.js)

See the repository root README for setup. Structure:

- `app/(public)` public booking website, `app/(auth)` login/OTP, `app/customer`, `app/professional`,
  `app/admin`, `app/super-admin` dashboards (separate shells per role).
- `components/ui` shadcn-style primitives, `components/layout` shells.
- `features/` domain modules, `hooks/`, `lib/` (API client, env, utils), `services/` API calls, `types/`.
