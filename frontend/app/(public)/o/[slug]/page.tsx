import { redirectTo } from "./redirect-to";

type Search = Record<string, string | string[] | undefined>;

export default async function LegacyRedirect({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<Search> }) {
  const { slug } = await params;
  redirectTo(`/${encodeURIComponent(slug)}`, await searchParams);
}
