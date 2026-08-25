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
    <nav className="sticky top-0 z-50 border-b border-border/40 bg-background/85 backdrop-blur-2xl px-8 py-3.5 flex items-center justify-between">
      <Link href="/" className="flex items-center gap-3 text-primary font-semibold text-base tracking-tight">
        <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center border border-primary/20">
          <Cpu size={16} className="text-primary" />
        </div>
        TERAFAC
      </Link>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-foreground/90 bg-card px-3 py-1.5 rounded-lg border border-border/50">{user.username}</span>
        <button
          onClick={handleLogout}
          className="w-8 h-8 rounded-lg flex items-center justify-center text-foreground/60 hover:text-foreground hover:bg-card border border-transparent hover:border-border/50 transition-all cursor-pointer"
          title="Logout"
        >
          <LogOut size={16} />
        </button>
      </div>
    </nav>
  );
}
