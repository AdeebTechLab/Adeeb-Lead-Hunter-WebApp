export default function Loader({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loader-wrap" aria-label={label}>
      <span className="loader" />
    </div>
  )
}
