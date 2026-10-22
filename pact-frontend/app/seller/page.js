'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { submitDeliverable, getPact } from '../../lib/api';
import ProtectedRoute from '../components/ProtectedRoute';

export default function SellerPortalPage() {
  const [pactId, setPactId] = useState('');
  const [jsonText, setJsonText] = useState('');

  // Contract details from backend
  const [pactData, setPactData] = useState(null);
  const [fetchingPact, setFetchingPact] = useState(false);
  const [wasRevision, setWasRevision] = useState(false);

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [successResponse, setSuccessResponse] = useState(null);

  const fetchContractData = useCallback(async (idToFetch) => {
    const trimmed = (idToFetch || '').trim();
    if (!trimmed) {
      setPactData(null);
      return;
    }
    try {
      setFetchingPact(true);
      const data = await getPact(trimmed);
      setPactData(data);
    } catch (err) {
      setPactData(null);
    } finally {
      setFetchingPact(false);
    }
  }, []);

  // Automatically read pactId from query params if redirected from buyer dashboard
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const paramId = params.get('pactId');
      if (paramId) {
        setPactId(paramId);
        fetchContractData(paramId);
      }
    }
  }, [fetchContractData]);

  // Fetch contract state when pactId looks like a valid UUID
  useEffect(() => {
    const trimmedId = pactId.trim();
    const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

    if (UUID_REGEX.test(trimmedId)) {
      fetchContractData(trimmedId);
    } else if (!trimmedId) {
      setPactData(null);
    }
  }, [pactId, fetchContractData]);

  const isRevisionRequested = pactData?.state === 'REVISION_REQUESTED';
  const isVoidedMaxAttempts =
    pactData?.state === 'VOIDED' &&
    typeof pactData?.current_attempt === 'number' &&
    typeof pactData?.max_attempts === 'number' &&
    pactData.current_attempt >= pactData.max_attempts;

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

    if (isVoidedMaxAttempts) {
      setError('Contract Voided: Maximum submission attempts exceeded.');
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
      setWasRevision(isRevisionRequested);
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
    setPactData(null);
    setWasRevision(false);
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
            {/* Amber Feedback Banner for REVISION_REQUESTED */}
            {isRevisionRequested && pactData && (
              <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-200">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-full bg-amber-500/20 p-1 text-amber-400">
                    <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div className="flex-1 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <h2 className="text-sm font-semibold text-amber-300">
                        Revision Required (Attempt {pactData.current_attempt} of {pactData.max_attempts})
                      </h2>
                      <span className="rounded-full border border-amber-500/30 bg-amber-500/20 px-2 py-0.5 font-mono text-[10px] font-medium text-amber-300 uppercase">
                        Action Needed
                      </span>
                    </div>

                    {pactData.last_rejection_reason && (
                      <div className="rounded-lg border border-amber-500/20 bg-slate-950/70 p-3 font-mono text-xs text-slate-200">
                        <span className="block text-[10px] font-semibold uppercase tracking-wider text-amber-400/80 mb-1">
                          AI Verification Rationale
                        </span>
                        <p className="whitespace-pre-wrap text-slate-300">
                          {pactData.last_rejection_reason}
                        </p>
                      </div>
                    )}

                    {Array.isArray(pactData.last_rejection_flags) && pactData.last_rejection_flags.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                        <span className="text-[11px] font-medium text-amber-300/80">Flagged Issues:</span>
                        {pactData.last_rejection_flags.map((flag, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center rounded-md border border-amber-500/30 bg-amber-500/20 px-2 py-0.5 font-mono text-[11px] font-semibold text-amber-200"
                          >
                            [{flag}]
                          </span>
                        ))}
                      </div>
                    )}

                    <p className="text-[11px] text-amber-300/90 pt-0.5 font-medium">
                      Please correct the flagged records and resubmit before the deadline.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Rose Error Banner for VOIDED & max attempts reached */}
            {isVoidedMaxAttempts && pactData && (
              <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-xs text-rose-300">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-full bg-rose-500/20 p-1 text-rose-400">
                    <svg className="h-4 w-4 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                      <path
                        fillRule="evenodd"
                        d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-rose-300">
                      Contract Voided: Maximum submission attempts exceeded.
                    </h2>
                    <p className="mt-1 text-[11px] text-rose-300/80">
                      All {pactData.max_attempts} allowed submission attempts have been exhausted. The escrow funds hold has been voided.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Contract ID Input */}
            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="pactId" className="block text-xs font-semibold uppercase tracking-wider text-slate-300">
                  Contract ID (Pact UUID)
                </label>
                {fetchingPact && (
                  <span className="flex items-center gap-1.5 text-[11px] text-indigo-400">
                    <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                    </svg>
                    Checking status...
                  </span>
                )}
              </div>
              <input
                id="pactId"
                type="text"
                required
                disabled={loading || isVoidedMaxAttempts}
                value={pactId}
                onChange={(e) => setPactId(e.target.value)}
                onBlur={() => {
                  const trimmed = pactId.trim();
                  if (trimmed && trimmed.length >= 32) {
                    fetchContractData(trimmed);
                  }
                }}
                placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000"
                className="mt-1.5 block w-full rounded-lg border border-slate-700 bg-slate-950/60 py-2.5 px-3.5 font-mono text-sm text-white placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
              />
              {pactData ? (
                <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                  <span className="text-slate-400">Contract State:</span>
                  <span className={`font-mono font-semibold ${
                    isRevisionRequested
                      ? 'text-amber-400'
                      : pactData.state === 'AUTHORIZED'
                      ? 'text-emerald-400'
                      : pactData.state === 'VOIDED'
                      ? 'text-rose-400'
                      : 'text-indigo-400'
                  }`}>
                    {pactData.state}
                  </span>
                  <span className="text-slate-600">&bull;</span>
                  <span className="text-slate-400">
                    Attempt {pactData.current_attempt || 1} of {pactData.max_attempts || 3}
                  </span>
                </div>
              ) : (
                <p className="mt-1 text-[11px] text-slate-500">
                  The agreement must be in <span className="text-slate-300 font-medium">AUTHORIZED</span> or <span className="text-amber-400 font-medium">REVISION_REQUESTED</span> state before deliverables can be processed.
                </p>
              )}
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
                  disabled={loading || isVoidedMaxAttempts}
                  className="text-xs text-indigo-400 hover:text-indigo-300 disabled:opacity-50 font-medium"
                >
                  Load Sample Dataset
                </button>
              </div>
              <textarea
                id="jsonPayload"
                rows={10}
                required
                disabled={loading || isVoidedMaxAttempts}
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder={`[\n  {\n    "id": 1,\n    "text": "Clean outcome dataset record..."\n  },\n  {\n    "id": 2,\n    "text": "Normalized data record..."\n  }\n]`}
                className="mt-1.5 block w-full rounded-lg border border-slate-700 bg-slate-950/70 p-3.5 font-mono text-xs text-slate-200 placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
              />
              <p className="mt-1.5 text-[11px] text-slate-500">
                Must be a valid <span className="text-slate-300 font-medium">JSON array</span> containing at least 2 records. Groq LLM evaluates this payload for prompt injections and schema consistency.
              </p>
            </div>

            {/* Submit Button with Dynamic Revision Text & Loading State */}
            <button
              type="submit"
              disabled={loading || isVoidedMaxAttempts}
              className={`mt-2 flex w-full items-center justify-center rounded-lg px-4 py-3 text-sm font-semibold text-white shadow-lg transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-900 disabled:cursor-not-allowed disabled:opacity-60 ${
                isVoidedMaxAttempts
                  ? 'bg-rose-900/60 text-rose-300 shadow-none border border-rose-800/50'
                  : isRevisionRequested
                  ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-600/20 focus:ring-amber-500'
                  : 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-600/20 focus:ring-indigo-500'
              }`}
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4 animate-spin text-white" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  Analyzing Payload...
                </span>
              ) : isVoidedMaxAttempts ? (
                'Contract Voided (Max Attempts Exceeded)'
              ) : isRevisionRequested ? (
                `Resubmit Revised Deliverable (Attempt ${(pactData?.current_attempt || 1) + 1}/${pactData?.max_attempts || 3})`
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
                {wasRevision
                  ? 'Revised Deliverable Submitted! Groq AI is re-evaluating the payload. Check the ledger for real-time status.'
                  : 'Deliverable Submitted! Groq AI is currently verifying the payload. Check the ledger for real-time status.'}
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
                <span className="font-semibold text-indigo-400">
                  {wasRevision ? 'SUBMITTED (Revision Queued)' : 'SUBMITTED (In Verification Queue)'}
                </span>
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
