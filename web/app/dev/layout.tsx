import { notFound } from "next/navigation";

/**
 * Everything under /dev exists to be looked at while the workbench is built,
 * and 404s in a production build so it cannot ship by accident.
 */
export default function DevLayout({ children }: { children: React.ReactNode }) {
  if (process.env.NODE_ENV === "production") notFound();
  return children;
}
