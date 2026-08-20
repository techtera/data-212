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
    <nav className="border-b border-border bg-card px-6 py-3 flex items-center justify-between">
      <Link href="/" className="flex items-center gap-2 text-primary font-semibold text-lg">
        <Cpu size={22} />
        TERAFAC
      </Link>
      <div className="flex items-center gap-4">
        <span className="text-sm text-muted">{user.username}</span>
        <button
          onClick={handleLogout}
          className="text-muted hover:text-foreground transition-colors cursor-pointer"
          title="Logout"
        >
          <LogOut size={18} />
        </button>
      </div>
    </nav>
  );
}
