"use client";

import * as React from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface CodeBlockProps {
  code: string;
  language?: string;
  className?: string;
}

export function CodeBlock({ code, language = "python", className }: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = (filename: string) => {
    const blob = new Blob([code], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={cn("relative rounded-lg border bg-zinc-950 p-4 font-mono text-sm overflow-x-auto", className)}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground uppercase">{language}</span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" onClick={() => handleDownload("inference.py")} title="Download .py">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
          </Button>
          <Button variant="ghost" size="icon" onClick={handleCopy} title="Copy">
            {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>
      </div>
      <pre className="text-zinc-100"><code>{code}</code></pre>
    </div>
  );
}