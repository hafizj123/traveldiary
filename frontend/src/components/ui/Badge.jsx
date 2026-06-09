export default function Badge({ children, color = 'slate' }) {
  const colors = {
    slate:   'bg-slate-100 text-slate-700',
    blue:    'bg-blue-100 text-blue-700',
    green:   'bg-green-100 text-green-700',
    red:     'bg-red-100 text-red-700',
    amber:   'bg-amber-100 text-amber-700',
    purple:  'bg-purple-100 text-purple-700',
    primary: 'bg-primary-100 text-primary-700',
  }
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colors[color] || colors.slate}`}>
      {children}
    </span>
  )
}
