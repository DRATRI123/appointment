"use client";

/**
 * A patient's bookings at one clinic. Bookings made in this browser: the booking page keeps each appointment's
 * private access token in localStorage (key `ap.appt.<reference>`). Signed in (one-time code to their mobile number or
 * email): every booking made with that number or email, on any device, without the private links.
 */
import { useQuery } from "@tanstack/react-query";
import { customerBooking, publicBooking } from "@/services/booking";
import type { Appointment } from "@/types/booking";

/** ``token`` is empty for bookings shown through the patient's account (the page opens them without a link). */
export interface DeviceBooking { appointment: Appointment; token: string }

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

export function useDeviceBookings(slug: string, signedIn = false) {
  return useQuery({
    queryKey: ["device-bookings", slug, signedIn],
    queryFn: async (): Promise<{ upcoming: DeviceBooking[]; past: DeviceBooking[] }> => {
      const account: DeviceBooking[] = signedIn
        ? await customerBooking.mine().then((rows) => rows.filter((a) => a.organization_slug === slug).map((appointment) => ({ appointment, token: "" }))).catch(() => [])
        : [];
      const results = await Promise.all(stored().map(async ({ reference, token }): Promise<DeviceBooking | null> => {
        try {
          const appointment = await publicBooking.status(slug, reference, token);
          return appointment.organization_slug === slug ? { appointment, token } : null;
        } catch {
          return null; // another clinic's booking, or no longer available
        }
      }));
      const device = results.filter((x): x is DeviceBooking => !!x);
      const seen = new Set(device.map((b) => b.appointment.reference));
      const list = [...device, ...account.filter((b) => !seen.has(b.appointment.reference))];
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
