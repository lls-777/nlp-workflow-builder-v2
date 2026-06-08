import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "自然语言工作助手",
  description: "用自然语言创建并运行文件处理流程"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
