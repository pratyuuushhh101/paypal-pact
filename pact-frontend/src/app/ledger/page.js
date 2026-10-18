'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { getPact } from '../../lib/api';
import ProtectedRoute from '../components/ProtectedRoute';

export default function LedgerPage() {
  const [pactIdInput, setPactIdInput] = useState('');
  const [activePactId, setActivePactId] = useState(null);

  const [pactData, setPactData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isPolling, setIsPolling] = useState(false);

  // Auto-read ?pactId=... query param if redirected from Buyer or Seller portal
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const queryId = params.get('pactId');
      if (queryId) {
        setPactIdInput(queryId);
        setActivePactId(queryId.trim());
        setLoading(true);
      }
    }
  }, []);

  // Poll the backend every 3 seconds if a pact is active and not in a terminal state
  useEffect(() => {
    let intervalId;

    const fetchPactData = async () => {
      if (!activePactId) return;

      try {
        const data = await getPact(activePactId);
        setPactData(data);
        setError(null);
        setLoading(false);

        // Stop polling if the contract is finalized
        const terminalStates = ['CAPTURED', 'VOIDED', 'REJECTED'];
        if (terminalStates.includes(data.state)) {
          setIsPolling(false);
          clearInterval(intervalId);
        } else {
          setIsPolling(true);
        }
      } catch (err) {
        setError(err.message);
        setIsPolling(false);
        setLoading(false);
        if (intervalId) clearInterval(intervalId);
      }
    };

    if (activePactId) {
      fetchPactData();
      intervalId = setInterval(fetchPactData, 3000);
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [activePactId]);

  const handleTrack = (e) => {
    e.preventDefault();
    if (!pactIdInput.trim()) return;
    setError(null);
    setLoading(true);
    setActivePactId(pactIdInput.trim());
  };

  const getEventStyling = (action) => {
    switch (action) {
      case 'PACT_CREATED':
        return {
          color: 'text-slate-300',
          bg: 'bg-slate-500/20',
          border: 'border-slate-500/30',
          title: 'Contract Drafted',
        };
      case 'AUTHORIZED':
      case 'AUTHORIZED_VIA_WEBHOOK':
        return {
          color: 'text-emerald-400',
          bg: 'bg-emerald-500/20',
          border: 'border-emerald-500/30',
          title: 'Funds Locked in Escrow',
        };
      case 'DELIVERABLE_SUBMITTED':
        return {
          color: 'text-amber-400',
          bg: 'bg-amber-500/20',
          border: 'border-amber-500/30',
          title: 'Dataset Submitted',
        };
      case 'REVIEW_STARTED':
        return {
          color: 'text-indigo-400',
          bg: 'bg-indigo-500/20',
          border: 'border-indigo-500/30',
          title: 'Groq AI Verification In Progress',
        };
      case 'AI_VERIFICATION_PASSED':
        return {
          color: 'text-fuchsia-400',
          bg: 'bg-fuchsia-500/20',
          border: 'border-fuchsia-500/30',
          title: 'Groq AI Verification Passed',
        };
      case 'VERIFICATION_FAILED':
      case 'AI_VERIFICATION_FAILED':
        return {
          color: 'text-rose-400',
          bg: 'bg-rose-500/20',
          border: 'border-rose-500/30',
          title: 'AI Verification Rejected',
        };
      case 'FUNDS_CAPTURED':
        return {
          color: 'text-emerald-400',
          bg: 'bg-emerald-500/20',
          border: 'border-emerald-500/30',
          title: 'Payment Settled (Funds Captured)',
        };
      case 'FUNDS_VOIDED':
      case 'FUNDS_VOIDED_EXTERNALLY':
        return {
          color: 'text-rose-400',
          bg: 'bg-rose-500/20',
          border: 'border-rose-500/30',
          title: 'Escrow Refunded (Authorization Voided)',
        };
      case 'AI_SERVICE_ERROR':
        return {
          color: 'text-amber-400',
          bg: 'bg-amber-500/20',
          border: 'border-amber-500/30',
          title: 'AI Service Communication Warning',
        };
      case 'CAPTURE_FAILED':
      case 'VOID_FAILED':
        return {
          color: 'text-rose-400',
          bg: 'bg-rose-500/20',
          border: 'border-rose-500/30',
          title: 'PayPal Gateway Warning',
        };
      default:
        return {
          color: 'text-slate-400',
          bg: 'bg-slate-800',
          border: 'border-slate-700',
          title: action.replace(/_/g, ' '),
        };
    }
  };

  const entries = pactData?.ledger_entries || [];

  return (
    <ProtectedRoute>
      <main className="mx-auto w-full max-w-3xl px-4 py-8">
        <div className="relative rounded-2xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-xl">
        {/* Header */}
        <div className="mb-8 flex items-center justify-between border-b border-slate-800/80 pb-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">Live Audit Ledger</h1>
            <p className="text-xs text-slate-400">Real-time immutable contract state & AI verification audit trail</p>
          </div>
          {isPolling && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Live Polling (3s)
            </span>
          )}
        </div>

        {/* Search Form */}
        <form onSubmit={handleTrack} className="mb-8 flex gap-3">
          <input
            type="text"
            value={pactIdInput}
            onChange={(e) => setPactIdInput(e.target.value)}
            placeholder="Enter Contract ID (Pact UUID)..."
            className="block w-full rounded-lg border border-slate-700 bg-slate-950/60 py-2.5 px-4 font-mono text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            type="submit"
            className="flex shrink-0 items-center justify-center rounded-lg bg-indigo-600 px-6 py-2.5 text-sm font-semibold text-white transition-all hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900"
          >
            Track Contract
          </button>
        </form>

        {error && (
          <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
            {error}
          </div>
        )}

        {loading && (
          <div className="py-12 text-center text-slate-400 flex flex-col items-center justify-center gap-3">
            <svg className="h-6 w-6 animate-spin text-indigo-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span className="text-sm">Fetching ledger data...</span>
          </div>
        )}

        {/* Timeline Visualization */}
        {pactData && (
          <div className="space-y-8">
            <div className="flex justify-between items-end mb-6 rounded-xl border border-slate-800 bg-slate-950/40 p-4">
              <div>
                <p className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-1">Current State</p>
                <div className="flex items-center gap-2">
                  <span className="text-xl font-bold text-white">{pactData.state}</span>
                  {pactData.state === 'CAPTURED' && (
                    <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-xs font-semibold text-emerald-400">
                      Completed
                    </span>
                  )}
                  {pactData.state === 'VOIDED' && (
                    <span className="rounded bg-rose-500/20 px-2 py-0.5 text-xs font-semibold text-rose-400">
                      Refunded
                    </span>
                  )}
                  {pactData.state === 'IN_REVIEW' && (
                    <span className="rounded bg-indigo-500/20 px-2 py-0.5 text-xs font-semibold text-indigo-400 animate-pulse">
                      Analyzing
                    </span>
                  )}
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs uppercase tracking-wider text-slate-500 font-semibold mb-1">Escrow Amount</p>
                <p className="text-xl font-mono text-emerald-400 font-bold">${pactData.amount} {pactData.currency}</p>
              </div>
            </div>

            {entries.length === 0 ? (
              <p className="text-center text-xs text-slate-500 py-6">No ledger entries recorded yet for this contract.</p>
            ) : (
              <div className="relative border-l-2 border-slate-800 ml-4 pl-8 space-y-6">
                {[...entries].reverse().map((entry) => {
                  const style = getEventStyling(entry.action);

                  return (
                    <div key={entry.id} className="relative">
                      {/* Timeline Node */}
                      <div className={`absolute -left-[41px] top-1 h-5 w-5 rounded-full border-4 border-slate-900 ${style.bg} ${style.border}`} />

                      <div className="rounded-xl border border-slate-800/60 bg-slate-950/40 p-4 shadow-sm transition-all hover:border-slate-700/80">
                        <div className="flex justify-between items-start mb-2">
                          <h3 className={`text-sm font-bold ${style.color}`}>{style.title}</h3>
                          <span className="text-[10px] text-slate-500 font-mono">
                            {new Date(entry.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>

                        {/* Event Details formatting */}
                        {entry.details && Object.keys(entry.details).length > 0 && (
                          <div className="text-xs text-slate-400 space-y-1.5 mt-3 border-t border-slate-800/50 pt-2">
                            {Object.entries(entry.details).map(([key, value]) => {
                              if (key === 'confidence_score' && typeof value === 'number') {
                                return (
                                  <div key={key} className="flex justify-between bg-fuchsia-500/10 border border-fuchsia-500/20 rounded p-2 mt-2">
                                    <span className="text-fuchsia-300 font-medium">Groq Confidence Score:</span>
                                    <span className="font-mono font-bold text-fuchsia-400">{(value * 100).toFixed(1)}%</span>
                                  </div>
                                );
                              }
                              if (key === 'flags' && Array.isArray(value) && value.length > 0) {
                                return (
                                  <div key={key} className="flex items-center gap-1.5 mt-1">
                                    <span className="text-slate-500">Flags:</span>
                                    {value.map((flag, idx) => (
                                      <span key={idx} className="rounded bg-rose-500/10 border border-rose-500/20 px-1.5 py-0.5 text-[10px] font-mono text-rose-300">
                                        {flag}
                                      </span>
                                    ))}
                                  </div>
                                );
                              }
                              return (
                                <div key={key} className="flex justify-between break-all gap-4">
                                  <span className="text-slate-500 capitalize">{key.replace(/_/g, ' ')}:</span>
                                  <span className="font-mono text-slate-300 text-right">{String(value)}</span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </main>
    </ProtectedRoute>
  );
}
