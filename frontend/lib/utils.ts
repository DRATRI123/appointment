import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format integer paise as Indian rupees, e.g. 50000 -> ₹500.00 */
export function formatPaise(paise: number, currency = "INR") {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency }).format(paise / 100);
}
