import { Inbox } from 'lucide-react'

export default function EmptyState({ title = 'No records found' }: { title?: string }) {
  return (
    <div className="empty-state">
      <Inbox size={28} />
      <strong>{title}</strong>
    </div>
  )
}
