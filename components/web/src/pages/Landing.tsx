import { Link } from "react-router-dom";

export function Landing(): React.ReactElement {
  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-8">
      <div className="max-w-xl text-center">
        <h1 className="text-5xl font-bold text-slate-900">Shrink</h1>
        <p className="mt-4 text-lg text-slate-600">
          Short links, clear analytics. Built for makers who care about the click after the click.
        </p>
        <Link
          to="/login"
          className="inline-block mt-8 rounded-md bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500"
        >
          Sign in
        </Link>
      </div>
    </main>
  );
}
