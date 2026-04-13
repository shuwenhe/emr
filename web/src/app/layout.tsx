import type { Metadata } from "next";
import { ConditionalNav } from "./components/ConditionalNav";
import "./globals.css";

export const metadata: Metadata = {
  title: "张氏疼痛外治中心 红外热成像诊断平台",
  description: "红外热成像诊断与电子病历管理系统",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased">
        <ConditionalNav />
        {children}
      </body>
    </html>
  );
}
