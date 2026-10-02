import type {Metadata} from "next";
import "./globals.css";
import "./training-adjustments.css";
import TrainingChrome from "@/components/training-chrome";

export const metadata: Metadata = {title: "12345派单训练", description: "独立的12345热线派单业务训练系统"};

export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="zh-CN"><body><TrainingChrome>{children}</TrainingChrome></body></html>;
}
