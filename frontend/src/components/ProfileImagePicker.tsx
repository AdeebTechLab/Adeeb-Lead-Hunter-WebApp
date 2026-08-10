import { Camera, Minus, Plus, X } from 'lucide-react'
import { ChangeEvent, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'

const MAX_BYTES = 1024 * 1024
const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp']

async function loadImage(file: File): Promise<HTMLImageElement> {
  const source = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Could not read profile photo'))
    reader.readAsDataURL(file)
  })
  const image = new Image()
  image.decoding = 'async'
  image.src = source
  await image.decode()
  return image
}

async function createCenteredCrop(file: File, zoom: number): Promise<File> {
  const image = await loadImage(file)
  const canvas = document.createElement('canvas')
  const size = 512
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('Image crop is not supported in this browser')

  const shortest = Math.min(image.naturalWidth, image.naturalHeight)
  const sourceSize = Math.max(1, shortest / zoom)
  const sourceX = Math.max(0, (image.naturalWidth - sourceSize) / 2)
  const sourceY = Math.max(0, (image.naturalHeight - sourceSize) / 2)
  ctx.drawImage(image, sourceX, sourceY, sourceSize, sourceSize, 0, 0, size, size)

  let quality = 0.9
  let blob: Blob | null = null
  while (quality >= 0.55) {
    blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    if (blob && blob.size <= MAX_BYTES) break
    quality -= 0.08
  }
  if (!blob || blob.size > MAX_BYTES) throw new Error('The cropped photo could not be reduced below 1 MB')
  return new File([blob], 'profile.jpg', { type: 'image/jpeg' })
}

type Props = {
  onChange: (file: File | null) => void
  resetKey?: number
}

export default function ProfileImagePicker({ onChange, resetKey = 0 }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [sourceFile, setSourceFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)

  useEffect(() => {
    setSourceFile(null)
    setZoom(1)
    onChange(null)
  // resetKey intentionally controls the whole picker lifecycle.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey])

  useEffect(() => {
    if (!sourceFile) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(sourceFile)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [sourceFile])

  useEffect(() => {
    if (!sourceFile) return
    let active = true
    createCenteredCrop(sourceFile, zoom)
      .then((file) => { if (active) onChange(file) })
      .catch((error) => toast.error(error instanceof Error ? error.message : 'Could not crop profile photo'))
    return () => { active = false }
  }, [sourceFile, zoom, onChange])

  function selectFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!ACCEPTED.includes(file.type)) return toast.error('Use a JPEG, PNG or WebP image')
    if (file.size > MAX_BYTES) return toast.error('Profile photo must be 1 MB or smaller')
    setZoom(1)
    setSourceFile(file)
    onChange(file)
  }

  function clear() {
    setSourceFile(null)
    setZoom(1)
    onChange(null)
  }

  return (
    <div className="profile-picker">
      <input ref={inputRef} className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={selectFile} />
      <div className="profile-picker-row">
        <button type="button" className="profile-preview" onClick={() => inputRef.current?.click()} aria-label="Choose profile photo">
          {previewUrl ? <img src={previewUrl} alt="Profile crop preview" style={{ transform: `scale(${zoom})` }} /> : <Camera size={24} />}
        </button>
        <div className="profile-picker-copy">
          <strong>Profile photo <span>Optional</span></strong>
          <small>JPEG, PNG or WebP · maximum 1 MB</small>
          <div className="profile-picker-actions">
            <button type="button" className="button secondary compact" onClick={() => inputRef.current?.click()}>{previewUrl ? 'Change' : 'Choose photo'}</button>
            {previewUrl && <button type="button" className="icon-button compact-icon" onClick={clear} title="Remove photo"><X size={15} /></button>}
          </div>
        </div>
      </div>
      {previewUrl && (
        <label className="zoom-control">
          <span><Minus size={13} />Zoom<Plus size={13} /></span>
          <input type="range" min="1" max="3" step="0.05" value={zoom} onChange={(event) => setZoom(Number(event.target.value))} />
        </label>
      )}
    </div>
  )
}
