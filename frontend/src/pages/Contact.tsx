import { useState } from 'react'

const API = 'http://localhost:8000/api'

const MEMBERS = [
  { name: '待填写', major: '待填写', wechat: '待填写', intro: '团队成员介绍待补充', avatar: '' },
  { name: '待填写', major: '待填写', wechat: '待填写', intro: '团队成员介绍待补充', avatar: '' },
]

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
      const r = await fetch(`${API}/contact/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name.trim(), contact_info: contact.trim(), message: message.trim() }),
      })
      if (r.ok) {
        showToast('发送成功！我们会尽快联系你 ✨')
        setName(''); setContact(''); setMessage('')
      } else setMsg('发送失败，请稍后再试')
    } finally { setSubmitting(false) }
  }

  return (
    <div>
      {toast && <div className="toast toast-success">{toast}</div>}

      <div className="page-header">
        <h1>联系我们</h1>
        <p>想深入了解北科？直接联系学长学姐</p>
      </div>

      <div className="container">
        {/* 团队成员 */}
        <div className="section-title">团队成员</div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
          gap: '16px', marginBottom: '48px',
        }}>
          {MEMBERS.map((m, i) => (
            <div key={i} className="card" style={{
              textAlign: 'center', padding: '32px 20px',
              animation: `fadeIn 0.4s ${i * 80}ms both`,
            }}>
              {m.avatar ? (
                <img src={m.avatar} alt={m.name} style={{
                  width: '64px', height: '64px', borderRadius: '50%',
                  objectFit: 'cover', margin: '0 auto 16px',
                  boxShadow: '0 4px 16px rgba(61,50,38,0.12)',
                  border: '3px solid var(--paper)',
                }} />
              ) : (
                <div style={{
                  width: '64px', height: '64px', borderRadius: '50%',
                  background: 'linear-gradient(135deg, var(--accent-glow), var(--gold-light))',
                  color: 'var(--accent)', display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  margin: '0 auto 16px', fontSize: '1.5rem', fontWeight: 700,
                  boxShadow: '0 4px 16px rgba(61,50,38,0.1)',
                  border: '3px solid var(--paper)',
                }}>
                  {m.name[0]}
                </div>
              )}
              <h3 style={{
                fontFamily: 'var(--font-serif)', fontSize: '1.05rem',
                fontWeight: 700, color: 'var(--ink)', marginBottom: '4px',
              }}>
                {m.name}
              </h3>
              <p style={{ color: 'var(--accent)', fontSize: '0.84rem', fontWeight: 500, marginBottom: '6px' }}>
                {m.major}
              </p>
              <span className="tag">💬 微信：{m.wechat}</span>
              <p style={{
                marginTop: '12px', fontSize: '0.85rem', color: 'var(--ink-light)',
                lineHeight: 1.55,
              }}>
                {m.intro}
              </p>
            </div>
          ))}
        </div>

        <div className="ornament"><span>✦ 给我们留言 ✦</span></div>

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
            想深入了解某个专业或有其他问题？请留言给我们
          </p>
          <div className="form-group">
            <input value={name} onChange={e => setName(e.target.value)} placeholder="你的姓名" />
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
