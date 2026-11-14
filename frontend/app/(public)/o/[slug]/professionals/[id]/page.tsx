import { redirectTo } from "../../redirect-to";

type Search = Record<string, string | string[] | undefined>;

export default async function LegacyRedirect({ params, searchParams }: { params: Promise<{ slug: string; id: string }>; searchParams: Promise<Search> }) {
  const { slug, id } = await params;
  redirectTo(`/${encodeURIComponent(slug)}`, await searchParams, { doctor: id });
}
