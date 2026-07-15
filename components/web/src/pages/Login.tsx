export function Login(): React.ReactElement {
  return (
    <main className="min-h-screen bg-slate-50 flex items-center justify-center p-8">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-semibold text-slate-900">Sign in</h1>
        <p className="mt-2 text-sm text-slate-600">
          Auth UI lands in T10. This page is a placeholder route only.
        </p>
        <a
          href="/"
          className="mt-6 inline-block text-sm font-medium text-indigo-600 hover:text-indigo-500"
        >
          ← Back to home
        </a>
      </div>
    </main>
  );
}
