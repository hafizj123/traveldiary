import Button from './Button'

export default function RouteCheckConfirmModal({
  open,
  title = 'No Route Found',
  message,
  confirmLabel = 'Continue Anyway',
  cancelLabel = 'Cancel',
  onConfirm,
  onCancel,
  canConfirm = true,
}) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-[95] flex items-center justify-center bg-slate-900/45 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-500">
          {message}
        </p>
        <div className="mt-5 flex gap-3">
          <Button type="button" variant="secondary" className="flex-1" onClick={onCancel}>
            {cancelLabel}
          </Button>
          {canConfirm && (
            <Button type="button" className="flex-1" onClick={onConfirm}>
              {confirmLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
