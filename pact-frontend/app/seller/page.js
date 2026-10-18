'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { submitDeliverable } from '../../lib/api';
import ProtectedRoute from '../components/ProtectedRoute';

export default function SellerPortalPage() {
  const [pactId, setPactId] = useState('');
  const [jsonText, setJsonText] = useState('');

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successResponse, setSuccessResponse] = useState(null);

  // Automatically read pactId from query params if redirected from buyer dashboard
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const paramId = params.get('pactId');
      if (paramId) {
        setPactId(paramId);
      }
    }
  }, []);

  /**
   * Pre-fills a sample valid JSON array for testing.
   */
  const handleLoadSample = () => {
    setError(null);
    const sample = [
      { id: 1, item: "Clean sample record A", confidence: 0.98 },
      { id: 2, item: "Clean sample record B", confidence: 0.95 }
    ];
    setJsonText(JSON.stringify(sample, null, 2));
  };

  /**
   * Client-side validation and submission handler.
   */
  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    const trimmedPactId = pactId.trim();
    if (!trimmedPactId) {
      setError('Please provide a Contract ID (Pact UUID).');
      return;
    }

    if (!jsonText.trim()) {
      setError('Please provide a JSON dataset payload.');
      return;
    }

    // 1. JSON parse & Array structure validation
    let parsedPayload;
    try {
      parsedPayload = JSON.parse(jsonText);
    } catch (parseErr) {
      setError(`Invalid JSON syntax: ${parseErr.message}`);
      return;
    }

    if (!Array.isArray(parsedPayload)) {
      setError('Payload must be a JSON Array (e.g., [ {"id": 1, ...}, {"id": 2, ...} ]).');
      return;
    }

    if (parsedPayload.length < 2) {
      setError('Payload array must contain at least 2 records to meet deterministic criteria.');
      return;
    }

    // 2. Dispatch to backend API
    try {
      setLoading(true);
      const data = await submitDeliverable(trimmedPactId, parsedPayload);
      setSuccessResponse(data);
    } catch (apiErr) {
      setError(apiErr.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Reset the form to submit another deliverable.
   */
  const handleReset = () => {
    setSuccessResponse(null);
    setError(null);
    setPactId('');
    setJsonText('');
  };

  return (
    <ProtectedRoute>
      <main className="mx-auto w-full max-w-2xl px-4 py-8">
        <div className="relative rounded-2xl border border-slate-800 bg-slate-900/90 p-8 shadow-2xl backdrop-blur-xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between border-b border-slate-800/80 pb-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">Seller Portal: Submit Deliverable</h1>
            <p className="text-xs text-slate-400">Outcome-based Escrow Verification Protocol</p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-indigo-500/20 bg-indigo-500/10 px-2.5 py-1 text-xs font-medium text-indigo-400">
            <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
            AI Verifier
          </span>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-6 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 text-xs text-rose-300">
            <div className="flex items-center gap-2">
              <svg className="h-4 w-4 shrink-0 text-rose-400" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                  clipRule="evenodd"
                />
              </svg>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Submission Form */}
        {!successResponse ? (
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Contract ID Input */}
            <div>
              <label htmlFor="pactId" className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                Contract ID (Pact UUID)
              </label>
              <input
                id="pactId"
                type="text"
                required
                disabled={loading}
                value={pactId}
                onChange={(e) => setPactId(e.target.value)}
                placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000"
                className="mt-1.5 block w-full rounded-lg border border-slate-700 bg-slate-950/60 py-2.5 px-3.5 font-mono text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
              />
              <p className="mt-1 text-[11px] text-slate-500">
                The agreement must be in <span className="text-slate-300 font-medium">AUTHORIZED</span> state before deliverables can be processed.
              </p>
            </div>

            {/* JSON Dataset Textarea */}
            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="jsonPayload" className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Deliverable Dataset (JSON Array)
                </label>
                <button
                  type="button"
                  onClick={handleLoadSample}
                  disabled={loading}
                  className="text-xs text-indigo-400 hover:text-indigo-300 disabled:opacity-50 font-medium"
                >
                  Load Sample Dataset
                </button>
              </div>
              <textarea
                id="jsonPayload"
                rows={10}
                required
                disabled={loading}
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder={`[\n  {\n    "id": 1,\n    "text": "Clean outcome dataset record..."\n  },\n  {\n    "id": 2,\n    "text": "Normalized data record..."\n  }\n]`}
                className="mt-1.5 block w-full rounded-lg border border-slate-700 bg-slate-950/70 p-3.5 font-mono text-xs text-slate-200 placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
              />
              <p className="mt-1.5 text-[11px] text-slate-500">
                Must be a valid <span className="text-slate-300 font-medium">JSON array</span> containing at least 2 records. Groq LLM evaluates this payload for prompt injections and schema consistency.
              </p>
            </div>

            {/* Submit Button with Loading State */}
            <button
              type="submit"
              disabled={loading}
              className="mt-2 flex w-full items-center justify-center rounded-lg bg-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-600/20 transition-all hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Analyzing Payload...
                </span>
              ) : (
                'Submit for AI Verification'
              )}
            </button>
          </form>
        ) : (
          /* Success Banner State */
          <div className="space-y-6 text-center py-4">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-indigo-500/30 bg-indigo-500/10">
              <svg className="h-7 w-7 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>

            <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-5">
              <h3 className="text-sm font-semibold text-indigo-300">
                Deliverable Submitted! Groq AI is currently verifying the payload. Check the ledger for real-time status.
              </h3>
              <p className="mt-1 text-xs text-indigo-300/80">
                The Celery background worker has enqueued your dataset for deterministic and LLM quality checks.
              </p>
            </div>

            {/* Submission Metadata */}
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-xs space-y-2 text-left">
              <div className="flex justify-between text-slate-400">
                <span>Contract ID:</span>
                <span className="font-mono text-slate-200">{pactId}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Pact State:</span>
                <span className="font-semibold text-indigo-400">SUBMITTED (In Verification Queue)</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Verification Engine:</span>
                <span className="text-slate-300 font-mono">Groq (llama3-70b-8192)</span>
              </div>
            </div>

            <div className="flex flex-col gap-2 pt-2">
              <Link
                href={`/ledger?pactId=${pactId}`}
                className="w-full rounded-lg bg-fuchsia-600 px-4 py-2.5 text-xs font-semibold text-white transition-all hover:bg-fuchsia-500 shadow-md shadow-fuchsia-600/20 text-center"
              >
                Track in Live Ledger &rarr;
              </Link>
              <button
                onClick={handleReset}
                className="w-full rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-xs font-semibold text-slate-300 transition-colors hover:bg-slate-700 hover:text-white"
              >
                Submit Another Deliverable
              </button>
              <Link
                href="/"
                className="w-full text-center text-xs text-slate-500 hover:text-slate-400 py-1"
              >
                Return to Buyer Dashboard
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
    </ProtectedRoute>
  );
}
