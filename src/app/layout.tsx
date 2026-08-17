import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';
import { Toaster } from 'sonner';

export const metadata: Metadata = {
  title: 'TERAFAC - Model Fine-tuning Platform',
  description: 'Image segmentation model fine-tuning and evaluation platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        <AuthProvider>
          {children}
          <Toaster
            theme="dark"
            position="bottom-right"
            toastOptions={{
              style: {
                background: 'oklch(0.2 0.01 260)',
                border: '1px solid oklch(0.3 0.02 260)',
                color: 'oklch(0.95 0.01 260)',
              },
            }}
          />
        </AuthProvider>
      </body>
    </html>
  );
}
