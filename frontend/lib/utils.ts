import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format integer paise as Indian rupees, e.g. 50000 -> ₹500.00 */
export function formatPaise(paise: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(paise / 100);
}

/** Return a copy of an object without the given keys (used to drop display-only fields before sending to the API). */
export function omit<T extends object, K extends keyof T>(obj: T, ...keys: K[]): Omit<T, K> {
  const copy = { ...obj } as T;
  for (const key of keys) delete copy[key];
  return copy;
}
