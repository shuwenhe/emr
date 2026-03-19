"use client";

import { useState } from "react";

interface PDFViewerProps {
  pdfUrl: string;
  title: string;
  onClose: () => void;
}

export default function PDFViewer({ pdfUrl, title, onClose }: PDFViewerProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleIframeLoaded = () => {
    setLoading(false);
  };

  const handleIframeError = () => {
    setLoading(false);
    setError("浏览器内预览失败，请点击“新窗口打开”查看 PDF");
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full h-full max-w-4xl max-h-96 flex flex-col">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900 truncate">{title}</h2>
          <div className="flex items-center gap-2">
            <a
              href={pdfUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50"
            >
              新窗口打开
            </a>
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 text-2xl font-bold"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        <div className="relative flex-1 overflow-hidden bg-gray-100">
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-gray-100">
              <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
              <p className="mt-2 text-gray-600">加载中...</p>
            </div>
          )}

          {error && (
            <div className="absolute inset-0 z-20 flex flex-col items-center justify-center bg-gray-100 p-4 text-center">
              <p className="text-red-600 font-semibold">加载失败</p>
              <p className="text-gray-600 text-sm mt-2">{error}</p>
            </div>
          )}

          <iframe
            title={title}
            src={pdfUrl}
            className="h-full w-full border-0"
            onLoad={handleIframeLoaded}
            onError={handleIframeError}
          />
        </div>
      </div>
    </div>
  );
}
