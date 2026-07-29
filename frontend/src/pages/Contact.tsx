import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getPublicApiError, publicRequest } from '../config/publicApi'

export default function Contact() {
  const [name, setName] = useState('')
  const [contact, setContact] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState('')
  const [msg, setMsg] = useState('')

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(''), 2800) }

  const submit = async () => {
    if (!name.trim() || !message.trim()) return
    setSubmitting(true); setMsg('')
    try {
      const r = await publicRequest('/contact/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), contact_info: contact.trim(), message: message.trim() }),
      })
      if (r.ok) {
        showToast('发送成功，实践团管理员会查看这条留言 ✨')
        setName(''); setContact(''); setMessage('')
      } else setMsg(await getPublicApiError(r, '发送失败，请稍后再试'))
    } catch {
      setMsg('网络错误，请稍后再试')
    } finally { setSubmitting(false) }
  }

  return (
    <div>
      {toast && <div className="toast toast-success">{toast}</div>}

      <div className="page-header">
        <h1>联系我们</h1>
        <p>通过仅管理员可见的表单联系实践团</p>
      </div>

      <div className="container">
        {/* 留言表单 */}
        <div className="card" style={{
          padding: '32px',
          background: 'linear-gradient(135deg, var(--paper) 0%, var(--cream) 100%)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
            <span style={{ fontSize: '1.4rem' }}>📝</span>
            <h2 style={{
              fontFamily: 'var(--font-serif)', fontSize: '1.1rem',
              fontWeight: 700, color: 'var(--ink)',
            }}>
              给我们留言
            </h2>
          </div>
          <p style={{ color: 'var(--ink-light)', fontSize: '0.86rem', marginBottom: '22px' }}>
            想深入了解活动或申请删除此前提交的联系记录，都可以在这里留言。
          </p>
          <div className="blockquote-decorated" style={{ marginBottom: '18px', fontSize: '0.82rem' }}>
            表单内容仅管理员可见，并按90天规则自动清理；停机或故障期间可能延迟，恢复后补清。
            请勿提交身份证号、家庭住址等敏感信息。删除申请请提供大致提交时间、当时的称呼和内容线索，
            不需要提供身份证件。详见 <Link to="/privacy">隐私说明</Link>。
          </div>
          <div className="form-group">
            <input value={name} onChange={e => setName(e.target.value)}
              placeholder="称呼（必填，可以填写昵称）" />
          </div>
          <div className="form-group">
            <input value={contact} onChange={e => setContact(e.target.value)}
              placeholder="联系方式：QQ / 微信 / 手机（可选）" />
          </div>
          <div className="form-group">
            <textarea value={message} onChange={e => setMessage(e.target.value)}
              placeholder="你想了解什么？有什么疑问？" />
          </div>
          <button className="btn btn-primary" onClick={submit}
            disabled={submitting || !name.trim() || !message.trim()}>
            📨 {submitting ? '发送中…' : '发送留言'}
          </button>
          {msg && (
            <p style={{
              marginTop: '14px', fontSize: '0.86rem',
              color: msg.startsWith('发送失败') ? '#C94A4A' : 'var(--green)',
            }}>
              {msg}
            </p>
          )}
        </div>
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}
