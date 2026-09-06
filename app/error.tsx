"use client";

export default function DashboardError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="grid min-h-screen place-items-center bg-[#f4f6f8] px-4">
      <div className="w-full max-w-md rounded-2xl border border-rose-200 bg-rose-50 p-6 text-rose-900">
        <p className="font-bold">Something went wrong</p>
        <p className="mt-2 text-sm leading-6 text-rose-700">
          The dashboard hit an unexpected error while rendering. Your watchlist data
          on the server is unaffected.
        </p>
        <button
          onClick={reset}
          className="mt-4 rounded-xl border border-rose-300 bg-white px-4 py-2 text-sm font-semibold hover:bg-rose-100"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
