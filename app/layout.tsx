import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Observatorio Parlamentario · Distrito 8",
  description: "Piloto de datos públicos sobre actividad, asistencia y transparencia parlamentaria.",
  icons: { icon: "/favicon.svg" },
  openGraph: {
    title: "Observatorio Parlamentario · Distrito 8",
    description: "Actividad, asistencia y transparencia parlamentaria con fuentes oficiales.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="es"><body>{children}</body></html>;
}
