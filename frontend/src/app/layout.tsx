import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "红外热成像诊断平台",
  description: "红外热成像诊断与电子病历管理系统",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <nav className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
            <Link href="/" className="text-lg font-semibold text-slate-900 hover:text-blue-600">
              红外热成像诊断平台
            </Link>
            <div className="flex gap-6">
              <Link
                href="/"
                className="text-sm font-medium text-slate-700 hover:text-blue-600"
              >
                首页
              </Link>
              <Link
                href="/patients"
                className="text-sm font-medium text-slate-700 hover:text-blue-600"
              >
                患者登记
              </Link>
              <Link
                href="/upload"
                className="text-sm font-medium text-slate-700 hover:text-blue-600"
              >
                数据采集
              </Link>
              <Link
                href="/emr"
                className="text-sm font-medium text-slate-700 hover:text-blue-600"
              >
                诊断分析
              </Link>
              <Link
                href="/treatment"
                className="text-sm font-medium text-slate-700 hover:text-blue-600"
              >
                治疗方案
              </Link>
              <Link
                href="/comparison"
                className="text-sm font-medium text-slate-700 hover:text-blue-600"
              >
                疗效对比
              </Link>
            </div>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
