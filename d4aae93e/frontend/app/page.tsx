import CampusApp from "@/components/CampusApp";
import { loadSnapshot } from "@/lib/loadSnapshot";

export default async function Page() {
  const snapshot = await loadSnapshot();

  if (!snapshot) {
    return (
      <main className="grid min-h-screen place-items-center bg-ink p-8 text-slate-300">
        <div className="glass max-w-lg rounded-2xl p-8">
          <h1 className="text-xl font-semibold text-white">Snapshot not generated</h1>
          <p className="mt-3 text-sm text-slate-400">
            Run <code className="mono text-mint">python -m src.export_snapshot</code> from the repository
            root, then rebuild the frontend.
          </p>
        </div>
      </main>
    );
  }

  return <CampusApp snapshot={snapshot} />;
}
