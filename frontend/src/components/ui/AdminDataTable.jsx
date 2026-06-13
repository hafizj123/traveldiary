import { useEffect, useMemo, useState } from 'react'
import { ArrowUpDown, ChevronLeft, ChevronRight, Search } from 'lucide-react'

function normalizeValue(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return value
  if (typeof value === 'boolean') return value ? 1 : 0
  return String(value).toLowerCase()
}

function compareValues(left, right) {
  const leftValue = normalizeValue(left)
  const rightValue = normalizeValue(right)

  if (typeof leftValue === 'number' && typeof rightValue === 'number') {
    return leftValue - rightValue
  }

  return String(leftValue).localeCompare(String(rightValue), undefined, {
    numeric: true,
    sensitivity: 'base',
  })
}

function resolveCellValue(column, row) {
  if (column.sortValue) {
    return column.sortValue(row)
  }
  return row[column.key]
}

function resolveSearchText(columns, row) {
  return columns
    .map((column) => {
      if (column.searchValue) return column.searchValue(row)
      return row[column.key]
    })
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

export default function AdminDataTable({
  columns,
  rows,
  rowKey = 'id',
  title = '',
  searchable = true,
  searchPlaceholder = 'Search table',
  emptyMessage = 'No rows found.',
  initialSortKey = '',
  initialSortDirection = 'asc',
  initialPageSize = 8,
  pageSizeOptions = [5, 8, 12, 20, 50],
}) {
  const sortableColumns = useMemo(
    () => columns.filter((column) => column.sortable !== false),
    [columns],
  )
  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState(initialSortKey || sortableColumns[0]?.key || '')
  const [sortDirection, setSortDirection] = useState(initialSortDirection)
  const [pageSize, setPageSize] = useState(initialPageSize)
  const [page, setPage] = useState(1)

  const filteredRows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) return rows
    return rows.filter((row) => resolveSearchText(columns, row).includes(normalizedQuery))
  }, [columns, query, rows])

  const sortedRows = useMemo(() => {
    if (!sortKey) return filteredRows
    const targetColumn = columns.find((column) => column.key === sortKey)
    if (!targetColumn) return filteredRows

    return [...filteredRows].sort((left, right) => {
      const result = compareValues(resolveCellValue(targetColumn, left), resolveCellValue(targetColumn, right))
      return sortDirection === 'asc' ? result : -result
    })
  }, [columns, filteredRows, sortDirection, sortKey])

  const totalPages = Math.max(1, Math.ceil(sortedRows.length / pageSize))
  const pagedRows = useMemo(() => {
    const startIndex = (page - 1) * pageSize
    return sortedRows.slice(startIndex, startIndex + pageSize)
  }, [page, pageSize, sortedRows])

  useEffect(() => {
    setPage(1)
  }, [pageSize, query, rows.length])

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages)
    }
  }, [page, totalPages])

  const handleSort = (column) => {
    if (column.sortable === false) return
    if (sortKey === column.key) {
      setSortDirection((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(column.key)
    setSortDirection('asc')
  }

  const getRowKey = (row, index) => {
    if (typeof rowKey === 'function') return rowKey(row, index)
    return row[rowKey] ?? index
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="text-xs text-slate-500">
          {title ? `${title} · ` : ''}{filteredRows.length} row{filteredRows.length === 1 ? '' : 's'}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {searchable ? (
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={searchPlaceholder}
                className="w-64 rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
              />
            </label>
          ) : null}
          <select
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 focus:border-primary-500 focus:outline-none"
          >
            {pageSizeOptions.map((option) => (
              <option key={option} value={option}>{option} / page</option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className={`px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 ${column.headerClassName || ''}`}
                  >
                    {column.sortable === false ? (
                      column.label
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleSort(column)}
                        className="inline-flex items-center gap-1 text-left transition hover:text-primary-700"
                      >
                        {column.label}
                        <ArrowUpDown className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {pagedRows.length === 0 ? (
                <tr>
                  <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-slate-500">
                    {emptyMessage}
                  </td>
                </tr>
              ) : (
                pagedRows.map((row, index) => (
                  <tr key={getRowKey(row, index)} className="align-top hover:bg-slate-50/70">
                    {columns.map((column) => (
                      <td key={column.key} className={`px-4 py-3 text-sm text-slate-700 ${column.className || ''}`}>
                        {column.render ? column.render(row) : row[column.key] ?? '-'}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
        <span>
          Page {page} of {totalPages}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            disabled={page <= 1}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            Prev
          </button>
          <button
            type="button"
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
            disabled={page >= totalPages}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
