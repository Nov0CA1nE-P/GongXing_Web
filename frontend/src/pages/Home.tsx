import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { API_BASE_URL } from '../config/runtime'

interface Stats { published_qa: number; total_courseware: number; total_messages: number; total_likes: number }

const features = [
  {
    title: '课件展示', desc: '浏览课程课件与讲义，随时随地回顾课堂内容',
    link: '/courseware', icon: '📖', tag: '学习资料',
  },
  {
    title: '留言板', desc: '写下感想与反馈，和同学们一起交流讨论',
    link: '/guestbook', icon: '✉️', tag: '互动交流',
  },
  {
    title: '专业问答', desc: '有困惑？躬行启杭智能大模型为你答疑解惑',
    link: '/qanda', icon: '💡', tag: 'AI 助手',
  },
  {
    title: '专业探索', desc: '不知道学什么？通过互动地图发现适合你的方向',
    link: '/explore', icon: '🗺️', tag: '新功能',
  },
  {
    title: '联系我们', desc: '想深入了解北科？直接联系学长学姐',
    link: '/contact', icon: '🤝', tag: '联系方式',
  },
]

const statCards = [
  { key: 'published_qa', label: '已解答问题', icon: '💡' },
  { key: 'total_courseware', label: '课件数量', icon: '📖' },
  { key: 'total_messages', label: '留言互动', icon: '💬' },
  { key: 'total_likes', label: '收获点赞', icon: '❤️' },
]

export default function Home() {
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    fetch(`${API_BASE_URL}/qanda/stats`)
      .then(r => r.json())
      .then(setStats)
      .catch(() => {})
  }, [])

  return (
    <div>
      {/* Hero */}
      <div style={{
        textAlign: 'center', padding: '88px 28px 60px',
        maxWidth: '720px', margin: '0 auto', position: 'relative',
      }}>
        {/* 装饰 */}
        <div style={{ position: 'absolute', top: '40px', left: '8%', fontSize: '2rem', opacity: 0.18, transform: 'rotate(-15deg)' }}>🌸</div>
        <div style={{ position: 'absolute', top: '48px', right: '6%', fontSize: '1.6rem', opacity: 0.2, transform: 'rotate(10deg)' }}>🌿</div>
        <div style={{ position: 'absolute', bottom: '56px', left: '12%', fontSize: '1.4rem', opacity: 0.15 }}>✨</div>
        <div style={{ position: 'absolute', bottom: '48px', right: '10%', fontSize: '1.8rem', opacity: 0.12, transform: 'rotate(-8deg)' }}>🍃</div>

        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: '12px', marginBottom: '28px',
        }}>
          <span style={{ width: '32px', height: '1px', background: 'var(--gold)' }} />
          <span style={{
            fontSize: '0.78rem', fontWeight: 600, letterSpacing: '0.08em',
            color: 'var(--ink-lighter)', textTransform: 'uppercase',
          }}>
            北京科技大学 · 躬行启杭实践团
          </span>
          <span style={{ width: '32px', height: '1px', background: 'var(--gold)' }} />
        </div>

        <h1 style={{
          fontFamily: 'var(--font-serif)', fontSize: 'clamp(2rem, 5vw, 3rem)',
          fontWeight: 800, letterSpacing: '0.03em', lineHeight: 1.25,
          color: 'var(--ink)', marginBottom: '20px',
        }}>
          从专业认知<br />到梦想启航
        </h1>

        <p style={{
          fontSize: '1rem', color: 'var(--ink-light)', lineHeight: 1.8, marginBottom: '36px',
        }}>
          对大学专业感到迷茫是每位高中生都会经历的时刻。
          <br />我们在这里，帮你探索方向、解答疑惑，让前路多一份清晰、少一分彷徨。
        </p>

        <div style={{ display: 'flex', gap: '14px', justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link to="/qanda" className="btn btn-primary" style={{ padding: '12px 30px', fontSize: '0.9rem' }}>
            💡 向大模型提问
          </Link>
          <Link to="/aitest" className="btn btn-outline" style={{ padding: '12px 30px', fontSize: '0.9rem' }}>
            🧠 AI 性格测试
          </Link>
          <Link to="/scores" className="btn btn-outline" style={{ padding: '12px 30px', fontSize: '0.9rem' }}>
            📊 高考分数线
          </Link>
          <Link to="/explore" className="btn btn-outline" style={{ padding: '12px 30px', fontSize: '0.9rem' }}>
            🗺️ 探索专业地图
          </Link>
        </div>
      </div>

      {/* 数据看板 */}
      {stats && (
        <div className="container" style={{ paddingBottom: '40px' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: '12px',
          }}>
            {statCards.map(s => (
              <div key={s.key} className="card" style={{
                textAlign: 'center', padding: '24px 16px',
              }}>
                <div style={{ fontSize: '2rem', marginBottom: '6px' }}>{s.icon}</div>
                <div style={{
                  fontFamily: 'var(--font-serif)', fontSize: '1.8rem',
                  fontWeight: 800, color: 'var(--accent)',
                }}>
                  {stats[s.key as keyof Stats]}
                </div>
                <div style={{ color: 'var(--ink-lighter)', fontSize: '0.82rem', marginTop: '4px' }}>
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="ornament"><span>✦</span></div>

      {/* 功能导航 */}
      <div className="container" style={{ paddingBottom: '40px' }}>
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <div className="section-title" style={{ justifyContent: 'center' }}>探索平台</div>
          <p style={{ color: 'var(--ink-lighter)', fontSize: '0.88rem' }}>
            五大板块，涵盖你需要的所有功能
          </p>
        </div>

        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '14px',
        }}>
          {features.map(f => (
            <Link key={f.link} to={f.link} style={{ textDecoration: 'none' }}>
              <div className="card" style={{
                textAlign: 'center', cursor: 'pointer', padding: '28px 18px',
                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px',
              }}>
                <div style={{ fontSize: '2.2rem', filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.06))' }}>
                  {f.icon}
                </div>
                <span className="tag">{f.tag}</span>
                <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.05rem', fontWeight: 700, color: 'var(--ink)' }}>
                  {f.title}
                </h3>
                <p style={{ color: 'var(--ink-light)', fontSize: '0.82rem', lineHeight: 1.5 }}>
                  {f.desc}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div className="ornament"><span>✦ 关于我们 ✦</span></div>

      {/* 关于我们 */}
      <div className="container" style={{ paddingBottom: '60px' }}>
        <div className="card" style={{
          padding: '36px 32px',
          background: 'linear-gradient(135deg, var(--paper) 0%, var(--cream) 100%)',
        }}>
          <div style={{ maxWidth: '640px', margin: '0 auto' }}>
            <h2 style={{
              fontFamily: 'var(--font-serif)', fontSize: '1.3rem',
              fontWeight: 700, textAlign: 'center', marginBottom: '20px',
              color: 'var(--ink)',
            }}>
              躬行启杭专业科普体验实践团
            </h2>

            <div style={{ fontSize: '0.92rem', color: 'var(--ink-light)', lineHeight: 1.85 }}>
              <p style={{ marginBottom: '14px' }}>
                我们是来自<strong style={{ color: 'var(--accent)' }}>北京科技大学</strong>的社会实践团队，
                由一群热爱专业、乐于分享的学长学姐组成。
                我们正在<strong style={{ color: 'var(--accent)' }}>学军中学紫金港校区</strong>开展专业科普体验活动。
              </p>
              <p style={{ marginBottom: '14px' }}>
                我们深知，高中阶段对大学专业的认知往往充满了模糊和不确定——
                <em>"我好像对计算机感兴趣但不知道具体学什么"</em>、
                <em>"爸妈想让我学医但我自己也不确定"</em>……
                这些困惑，我们每个人都经历过。
              </p>
              <p style={{ marginBottom: '14px' }}>
                所以我们搭建了这个平台，希望用<strong style={{ color: 'var(--green)' }}>真实、易懂、有温度</strong>的方式，
                帮助每一位学军中学的同学了解大学专业、找到自己真正热爱的方向。
              </p>
            </div>

            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: '12px', marginTop: '24px', textAlign: 'center',
            }}>
              {[
                { emoji: '🎯', text: '专业科普讲座' },
                { emoji: '🤖', text: 'AI 智能答疑' },
                { emoji: '👥', text: '学长学姐交流' },
                { emoji: '📚', text: '优质课件资源' },
              ].map((item, i) => (
                <div key={i} style={{
                  padding: '14px 12px', background: 'white',
                  borderRadius: 'var(--radius-sm)', boxShadow: 'var(--shadow-sm)',
                }}>
                  <div style={{ fontSize: '1.6rem', marginBottom: '6px' }}>{item.emoji}</div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--ink)' }}>{item.text}</div>
                </div>
              ))}
            </div>

            <div style={{ textAlign: 'center', marginTop: '24px' }}>
              <Link to="/contact" className="btn btn-primary">
                🤝 联系我们
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
