import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { AnnouncementBanner } from "@/components/layout/announcement-banner";

export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <AnnouncementBanner />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </>
  );
}
