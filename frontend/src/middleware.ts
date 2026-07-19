import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const MAINTENANCE_PATH = "/manutencao";

// Ativado via env var MAINTENANCE_MODE=true no Vercel (Settings > Environment
// Variables) + redeploy. Desligado por padrão -- nunca derruba o site sozinho.
export function middleware(request: NextRequest) {
  if (process.env.MAINTENANCE_MODE !== "true") {
    return NextResponse.next();
  }

  const { pathname } = request.nextUrl;
  if (pathname.startsWith(MAINTENANCE_PATH)) {
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = MAINTENANCE_PATH;
  return NextResponse.rewrite(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|images).*)"],
};
