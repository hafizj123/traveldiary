export default function Input({
  label,
  error,
  className = '',
  ...props
}) {
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label className="text-sm font-medium text-slate-700">{label}</label>
      )}
      <input
        className={`w-full px-3 py-2 text-sm border rounded-lg bg-white
          focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent
          disabled:bg-slate-50 disabled:cursor-not-allowed
          ${error ? 'border-red-400' : 'border-slate-300'}
          ${className}`}
        {...props}
      />
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}
