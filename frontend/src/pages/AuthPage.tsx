import { ArrowRight, Bot, Eye, EyeOff, IdCard, LockKeyhole, Mail, MapPin, UserRound } from 'lucide-react'
import { FormEvent, useCallback, useState } from 'react'
import toast from 'react-hot-toast'
import { Link, useNavigate } from 'react-router-dom'
import ProfileImagePicker from '../components/ProfileImagePicker'
import { useAuth } from '../contexts/AuthContext'

export default function AuthPage({ mode }: { mode: 'login' | 'signup' }) {
  const { login, signup } = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [profileImage, setProfileImage] = useState<File | null>(null)
  const onProfileChange = useCallback((file: File | null) => setProfileImage(file), [])
  const [form, setForm] = useState({ name: '', cnic: '', city: '', email: '', password: '' })

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    try {
      if (mode === 'login') {
        await login(form.email, form.password)
      } else {
        const body = new FormData()
        body.append('name', form.name.trim())
        body.append('cnic', form.cnic.trim())
        body.append('city', form.city.trim())
        body.append('email', form.email.trim())
        body.append('password', form.password)
        if (profileImage) body.append('profile_image', profileImage)
        await signup(body)
      }
      navigate('/')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel auth-brand-panel">
        <div className="auth-brand">
          <div className="brand-mark large"><Bot size={30} /></div>
          <div><strong>Adeeb Lead Hunter</strong><span>Sales Intelligence Platform</span></div>
        </div>
        <div className="auth-value">
          <span className="eyebrow light">Sales intelligence</span>
          <h1>Find better leads.<br />Pitch with confidence.</h1>
        </div>
      </section>
      <section className={`auth-panel auth-form-panel ${mode === 'signup' ? 'signup-panel' : ''}`}>
        <form className="auth-form" onSubmit={submit}>
          <div>
            <span className="eyebrow">{mode === 'login' ? 'Workspace access' : 'New account'}</span>
            <h2>{mode === 'login' ? 'Sign in' : 'Create account'}</h2>
          </div>
          {mode === 'signup' && (
            <>
              <label>Full name<div className="input-with-icon"><UserRound size={18} /><input required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Full name" /></div></label>
              <label>CNIC<div className="input-with-icon"><IdCard size={18} /><input required inputMode="numeric" value={form.cnic} onChange={(e) => setForm({ ...form, cnic: e.target.value })} placeholder="35202-1234567-1" /></div></label>
              <label>City<div className="input-with-icon"><MapPin size={18} /><input required minLength={2} value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} placeholder="Lahore" /></div></label>
            </>
          )}
          <label>Email<div className="input-with-icon"><Mail size={18} /><input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="name@company.com" /></div></label>
          <label>Password<div className="input-with-icon"><LockKeyhole size={18} /><input type={showPassword ? 'text' : 'password'} minLength={8} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Minimum 8 characters" /><button type="button" onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
          {mode === 'signup' && <ProfileImagePicker onChange={onProfileChange} />}
          <button className="button primary auth-submit" disabled={loading}>{loading ? 'Please wait' : mode === 'login' ? 'Sign in' : 'Create account'}<ArrowRight size={18} /></button>
          <p className="auth-switch">{mode === 'login' ? 'Need an account?' : 'Already have access?'} <Link to={mode === 'login' ? '/signup' : '/login'}>{mode === 'login' ? 'Create account' : 'Sign in'}</Link></p>
        </form>
      </section>
    </main>
  )
}
