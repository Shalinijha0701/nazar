export default function DashboardLoading() {
  return (
    <div className="min-h-screen bg-[#f4f6f8]">
      <div className="mx-auto max-w-[1460px] px-4 py-8 sm:px-7 lg:px-10">
        <div className="h-8 w-64 animate-pulse rounded-lg bg-slate-200" />
        <div className="mt-3 h-4 w-96 max-w-full animate-pulse rounded bg-slate-200" />
        <div className="mt-8 h-52 animate-pulse rounded-3xl bg-slate-200" />
        <div className="mt-7 grid gap-4 xl:grid-cols-2">
          <div className="h-48 animate-pulse rounded-2xl bg-slate-200" />
          <div className="h-48 animate-pulse rounded-2xl bg-slate-200" />
        </div>
      </div>
    </div>
  );
}
