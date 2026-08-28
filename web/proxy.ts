import { NextResponse, type NextRequest } from "next/server";

/**
 * Expose the pathname to server components.
 *
 * The workbench layout is shared by all five perspectives -- deliberately, so
 * the panel group never unmounts and Monaco and the event stream survive
 * navigation -- but it has to pick that perspective's stored pane sizes before
 * the first byte of HTML. A layout receives no pathname, and reading it on the
 * client would put the layout back behind an effect, which is the flash this
 * whole design exists to remove.
 *
 * `proxy` rather than `middleware`: Next 16 renamed the convention and warns
 * on the old name at every build.
 */
export default function proxy(request: NextRequest) {
  const headers = new Headers(request.headers);
  headers.set("x-pathname", request.nextUrl.pathname);
  return NextResponse.next({ request: { headers } });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
