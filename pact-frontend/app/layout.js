'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { PayPalScriptProvider } from '@paypal/react-paypal-js';
import { isLoggedIn, clearTokens } from '../lib/auth';
import './globals.css';

export default function RootLayout({ children }) {
  const pathname = usePathname();
  const router = useRouter();
  const [authenticated, setAuthenticated] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setAuthenticated(isLoggedIn());
  }, [pathname]);

  const handleLogout = () => {
    clearTokens();
    setAuthenticated(false);
    router.push('/login');
  };

  const initialPayPalOptions = {
    clientId: process.env.NEXT_PUBLIC_PAYPAL_CLIENT_ID || 'test',
    intent: 'authorize',
    currency: 'USD',
  };

  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-slate-950 font-sans text-slate-100 antialiased selection:bg-emerald-500/30 selection:text-emerald-300">
        <PayPalScriptProvider options={initialPayPalOptions}>
          <div className="relative flex min-h-screen flex-col overflow-hidden bg-slate-950">
            {/* Ambient background glows */}
            <div className="pointer-events-none absolute -top-40 left-1/2 -z-10 h-[500px] w-[600px] -translate-x-1/2 rounded-full bg-emerald-500/10 blur-[120px]" />
            <div className="pointer-events-none absolute -bottom-40 left-1/2 -z-10 h-[500px] w-[600px] -translate-x-1/2 rounded-full bg-indigo-500/10 blur-[120px]" />

            {/* Global Navbar */}
            <header className="sticky top-0 z-50 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
              <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3.5">
                <Link href="/" className="flex items-center gap-2.5">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/30">
                    <span className="text-emerald-400 font-bold text-sm">P</span>
                  </div>
                  <div>
                    <span className="font-bold tracking-tight text-white text-base">Pact Core</span>
                    <span className="ml-2 rounded border border-slate-700/60 bg-slate-800/60 px-1.5 py-0.5 text-[10px] font-mono text-slate-400">
                      Escrow v1.0
                    </span>
                  </div>
                </Link>

                {mounted && authenticated ? (
                  <nav className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
                    <Link
                      href="/"
                      className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
                        pathname === '/'
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Buyer Dashboard
                    </Link>
                    <Link
                      href="/seller"
                      className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
                        pathname === '/seller'
                          ? 'bg-indigo-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Seller Portal
                    </Link>
                    <Link
                      href="/ledger"
                      className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
                        pathname === '/ledger'
                          ? 'bg-fuchsia-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Live Ledger
                    </Link>
                  </nav>
                ) : mounted && !authenticated ? (
                  <nav className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
                    <Link
                      href="/login"
                      className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
                        pathname === '/login'
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Sign In
                    </Link>
                    <Link
                      href="/register"
                      className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition-all ${
                        pathname === '/register'
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Register
                    </Link>
                  </nav>
                ) : (
                  <div className="h-8 w-48" />
                )}

                <div className="hidden sm:flex items-center gap-3">
                  {mounted && authenticated ? (
                    <button
                      onClick={handleLogout}
                      className="rounded-lg border border-slate-800 bg-slate-900/80 px-3 py-1.5 text-xs font-medium text-slate-300 transition-all hover:border-rose-500/40 hover:bg-rose-500/10 hover:text-rose-400"
                    >
                      Logout
                    </button>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                      <span className="text-xs font-mono text-slate-400">API: 127.0.0.1:8000</span>
                    </div>
                  )}
                </div>
              </div>
            </header>

            {/* Main Content Area */}
            <div className="flex flex-1 items-center justify-center py-10">
              {children}
            </div>
          </div>
        </PayPalScriptProvider>
      </body>
    </html>
  );
}
