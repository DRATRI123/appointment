import { redirectTo } from "../../redirect-to";

type Search = Record<string, string | string[] | undefined>;

export default async function LegacyRedirect({ params, searchParams }: { params: Promise<{ slug: string; reference: string }>; searchParams: Promise<Search> }) {
  const { slug, reference } = await params;
  redirectTo(`/${encodeURIComponent(slug)}/appointments/${encodeURIComponent(reference)}`, await searchParams);
}
