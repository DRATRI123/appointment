"use client";

/**
 * Bookings made in this browser. The booking page keeps each appointment's private access token in localStorage
 * (key `ap.appt.<reference>`) so the patient can reopen it; here we list them for one clinic. Nothing is shared with
 * other devices; signed-in patients see all their bookings in their account.
 */
import { useQuery } from "@tanstack/react-query";
import { publicBooking } from "@/services/booking";
import type { AppointmentDetail } from "@/types/booking";

export interface DeviceBooking { appointment: AppointmentDetail; token: string }

function stored(): { reference: string; token: string }[] {
  try {
    const out: { reference: string; token: string }[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const key = window.localStorage.key(i) ?? "";
      if (!key.startsWith("ap.appt.")) continue;
      const token = window.localStorage.getItem(key) ?? "";
      const reference = key.slice("ap.appt.".length);
      if (/^APT-[A-Z0-9-]{4,60}$/.test(reference) && token) out.push({ reference, token });
    }
    return out.slice(-30);
  } catch {
    return [];
  }
}

const OPEN = new Set(["pending_payment", "pending_verification", "confirmed", "checked_in", "in_progress"]);

export function useDeviceBookings(slug: string) {
  return useQuery({
    queryKey: ["device-bookings", slug],
    queryFn: async (): Promise<{ upcoming: DeviceBooking[]; past: DeviceBooking[] }> => {
      const results = await Promise.all(stored().map(async ({ reference, token }) => {
        try {
          const appointment = await publicBooking.status(slug, reference, token);
          return appointment.organization_slug === slug ? { appointment, token } : null;
        } catch {
          return null; // another clinic's booking, or no longer available
        }
      }));
      const list = results.filter((x): x is DeviceBooking => !!x);
      const now = Date.now();
      const upcoming = list.filter((b) => OPEN.has(b.appointment.status) && new Date(b.appointment.end_at).getTime() > now)
        .sort((a, b) => a.appointment.start_at.localeCompare(b.appointment.start_at));
      const past = list.filter((b) => !upcoming.includes(b)).sort((a, b) => b.appointment.start_at.localeCompare(a.appointment.start_at));
      return { upcoming, past };
    },
    staleTime: 30_000,
    enabled: typeof window !== "undefined",
  });
}
