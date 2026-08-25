'use client';

import { useAuth } from '@/lib/auth-context';
import { LogOut, Cpu } from 'lucide-react';
import Link from 'next/link';
import { logout as apiLogout } from '@/lib/api';
import { useRouter } from 'next/navigation';

export function Navbar() {
  const { user, token, logout } = useAuth();
  const router = useRouter();

  const handleLogout = async () => {
    if (token) {
      try {
        await apiLogout(token);
      } catch {
        // ignore logout API errors
      }
    }
    logout();
    router.push('/login');
  };

  if (!user) return null;

  return (
    <nav className="sticky top-0 z-50 border-b border-border/50 bg-background/80 backdrop-blur-xl px-6 py-3 flex items-center justify-between">
      <Link href="/" className="flex items-center gap-2.5 text-primary font-semibold text-lg tracking-tight">
        <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center">
          <Cpu size={16} className="text-primary" />
        </div>
        TERAFAC
      </Link>
      <div className="flex items-center gap-3">
        <span className="text-xs text-muted bg-card/60 px-2.5 py-1 rounded-full">{user.username}</span>
        <button
          onClick={handleLogout}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-muted hover:text-foreground hover:bg-card/80 transition-all cursor-pointer"
          title="Logout"
        >
          <LogOut size={15} />
        </button>
      </div>
    </nav>
  );
}
