'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { PayPalButtons } from '@paypal/react-paypal-js';
import { createPact } from '../lib/api';
import ProtectedRoute from './components/ProtectedRoute';

export default function BuyerDashboardPage() {
  const [amount, setAmount] = useState('150.00');
  const deliverableType = 'JSON_DATASET';

  // API & Contract State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pactData, setPactData] = useState(null); // { id, paypalOrderId, amount, currency }
  const [isApproved, setIsApproved] = useState(false);
  const [copied, setCopied] = useState(false);

  /**
   * Handle initial contract creation request to Django backend.
   */
  const handleCreateContract = async (e) => {
    e.preventDefault();
    setError(null);

    const parsedAmount = parseFloat(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setError('Please provide a valid amount greater than $0.00');
      return;
    }

    try {
      setLoading(true);
      const data = await createPact(parsedAmount, deliverableType);

      const pactObj = data.pact || data;
      setPactData({
        id: pactObj.id,
        paypalOrderId: pactObj.paypal_order_id,
        amount: pactObj.amount || parsedAmount.toFixed(2),
        currency: pactObj.currency || 'USD',
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Reset state to create a new pact.
   */
  const handleReset = () => {
    setPactData(null);
    setIsApproved(false);
    setError(null);
    setAmount('150.00');
    setCopied(false);
  };

  /**
   * Copy Pact UUID to clipboard for convenient seller submission.
   */
  const handleCopyId = () => {
    if (pactData?.id && typeof navigator !== 'undefined') {
      navigator.clipboard.writeText(pactData.id);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <ProtectedRoute>
      <main className="mx-auto w-full max-w-lg px-4">
        <div className="relative rounded-2xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-xl transition-all">
        {/* Header with status badge */}
        <div className="mb-6 flex items-center justify-between border-b border-slate-800/80 pb-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">Escrow Agreement</h1>
            <p className="text-xs text-slate-400">AI-Verified Deliverable Protocol</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Live Escrow
          </span>
        </div>

        {/* Global Error Banner */}
        {error && (
          <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
            <div className="flex items-center gap-2">
              <svg className="h-4 w-4 shrink-0 text-rose-400" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
              </svg>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Step 1: Draft Contract Creation Form */}
        {!pactData && (
          <form onSubmit={handleCreateContract} className="space-y-5">
            <div>
              <label htmlFor="amount" className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Amount (USD)
              </label>
              <div className="relative mt-1.5 rounded-lg shadow-sm">
                <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3">
                  <span className="text-slate-500 sm:text-sm">$</span>
                </div>
                <input
                  id="amount"
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  disabled={loading}
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0.00"
                  className="block w-full rounded-lg border border-slate-700 bg-slate-950/60 py-2.5 pl-7 pr-3 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500 disabled:opacity-50"
                />
              </div>
            </div>

            <div>
              <label htmlFor="deliverableType" className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Deliverable Type
              </label>
              <div className="relative mt-1.5">
                <input
                  id="deliverableType"
                  type="text"
                  readOnly
                  value={deliverableType}
                  className="block w-full cursor-not-allowed rounded-lg border border-slate-800 bg-slate-950/40 py-2.5 px-3 text-sm font-mono text-slate-400 focus:outline-none"
                />
                <span className="absolute inset-y-0 right-3 flex items-center text-xs font-medium text-slate-500">
                  Read-only
                </span>
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                Deliverables will be validated automatically using deterministic schemas and Groq LLM verification.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="mt-2 flex w-full items-center justify-center rounded-lg bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-600/20 transition-all hover:bg-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Initiating Contract...
                </span>
              ) : (
                'Create Contract'
              )}
            </button>
          </form>
        )}

        {/* Step 2: PayPal Authorization Stage */}
        {pactData && !isApproved && (
          <div className="space-y-6">
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 space-y-2 text-xs">
              <div className="flex justify-between items-center text-slate-400">
                <span>Contract ID:</span>
                <span className="font-mono text-slate-200">{pactData.id}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Escrow Total:</span>
                <span className="font-semibold text-emerald-400">${pactData.amount} {pactData.currency}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>PayPal Order:</span>
                <span className="font-mono text-slate-200">{pactData.paypalOrderId}</span>
              </div>
            </div>

            <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 text-xs text-amber-300">
              Complete authorization below to lock funds in escrow. Funds remain on hold until deliverable AI verification succeeds.
            </div>

            {/* PayPal Button Integration */}
            <div className="pt-2">
              <PayPalButtons
                style={{ layout: 'vertical', color: 'blue', shape: 'rect', label: 'pay' }}
                // Return pre-created PayPal Order ID from Django backend
                createOrder={() => pactData.paypalOrderId}
                // Approval: Update frontend UI without calling additional APIs
                onApprove={async () => {
                  setIsApproved(true);
                }}
                onError={(err) => {
                  console.error('PayPal Checkout Error:', err);
                  setError('PayPal encountered an issue during checkout. Please check sandbox credentials.');
                }}
              />
            </div>

            <button
              onClick={handleReset}
              className="w-full text-center text-xs text-slate-500 hover:text-slate-400"
            >
              Cancel and start over
            </button>
          </div>
        )}

        {/* Step 3: Success Confirmation State */}
        {isApproved && (
          <div className="space-y-5 text-center py-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <svg className="h-7 w-7 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
              </svg>
            </div>

            <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4">
              <h3 className="text-sm font-semibold text-emerald-300">
                Authorization Complete! Our backend webhooks are securing your funds.
              </h3>
              <p className="mt-1 text-xs text-emerald-400/80">
                Your payment authorization has been reserved in escrow.
              </p>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-xs text-left space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Pact ID:</span>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-slate-200">{pactData?.id}</span>
                  <button
                    onClick={handleCopyId}
                    className="rounded bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 hover:bg-slate-700"
                  >
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Status:</span>
                <span className="font-medium text-emerald-400">AUTHORIZED (Escrow Locked)</span>
              </div>
            </div>

            <div className="flex flex-col gap-2 pt-2">
              <Link
                href={`/seller?pactId=${pactData?.id || ''}`}
                className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 text-xs font-semibold text-white shadow-lg shadow-indigo-600/20 transition-all hover:bg-indigo-500 text-center"
              >
                Go to Seller Portal to Submit Dataset &rarr;
              </Link>
              <Link
                href={`/ledger?pactId=${pactData?.id || ''}`}
                className="w-full rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2 text-xs font-semibold text-fuchsia-400 transition-colors hover:bg-slate-700 hover:text-fuchsia-300 text-center"
              >
                View Live Audit Ledger &rarr;
              </Link>
              <button
                onClick={handleReset}
                className="w-full text-center text-xs text-slate-500 hover:text-slate-400 py-1"
              >
                Create Another Contract
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
    </ProtectedRoute>
  );
}