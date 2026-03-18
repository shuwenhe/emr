"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/", label: "首页" },
  { href: "/patients", label: "患者登记" },
  { href: "/upload", label: "数据采集" },
  { href: "/emr", label: "诊断分析" },
  { href: "/treatment", label: "治疗方案" },
  { href: "/comparison", label: "疗效对比" },
  { href: "/reports", label: "历史报告" },
  { href: "/archives", label: "归档管理" },
];

/** 在微信自助登记页面不显示后台导航栏 */
export function ConditionalNav() {
  const pathname = usePathname();
  if (pathname.startsWith("/self-register")) return null;

  return (
    <nav className="sticky top-0 z-50 border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-lg font-semibold text-slate-900 hover:text-blue-600">
          红外热成像诊断平台
        </Link>
        <div className="flex gap-6">
          {NAV_LINKS.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="text-sm font-medium text-slate-700 hover:text-blue-600"
            >
              {label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
