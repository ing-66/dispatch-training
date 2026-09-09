import type {Metadata} from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {title: "12345派单训练", description: "独立的12345热线派单业务训练系统"};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body>
    <header className="topbar"><Link href="/training" className="brand"><span className="brandMark">派</span><span>12345派单训练</span></Link><span className="tag">业务能力训练</span></header>
    <main className="shell">{children}</main>
  </body></html>;
}
