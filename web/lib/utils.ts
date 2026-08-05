import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge class names, letting the last conflicting utility win.
 *
 * `clsx` flattens conditionals; `twMerge` resolves Tailwind conflicts, so a
 * caller passing `className="px-6"` to a component whose base is `px-4` gets
 * px-6 rather than two competing declarations decided by stylesheet order.
 * Every vendored shadcn component expects this to exist at this path.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
