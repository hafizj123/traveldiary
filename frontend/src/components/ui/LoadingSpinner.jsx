export default function LoadingSpinner({ size = 'md', className = '' }) {
  const sz = { xs: 'w-3.5 h-3.5', sm: 'w-4 h-4', md: 'w-8 h-8', lg: 'w-12 h-12' }[size] || 'w-8 h-8'
  return (
    <svg className={`loading-spinner block ${sz} ${className}`} fill="none" viewBox="0 0 48 48" role="status" aria-label="Loading">
      <circle cx="24" cy="24" r="16" stroke="#ddd6fe" strokeWidth="9" />
      <circle
        cx="24"
        cy="24"
        r="16"
        stroke="#7c6ee6"
        strokeWidth="9"
        strokeDasharray="26 100"
        strokeLinecap="butt"
        transform="rotate(-100 24 24)"
      />
    </svg>
  )
}
