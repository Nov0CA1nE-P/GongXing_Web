import { useState } from 'react'
import { Link } from 'react-router-dom'
import { categories, type Category, type Major } from '../data/majors'

export default function Explore() {
  const [selectedCat, setSelectedCat] = useState<Category | null>(null)
  const [selectedMajor, setSelectedMajor] = useState<Major | null>(null)
  const [expandedCat, setExpandedCat] = useState<string | null>(null)

  const resetCat = () => { setSelectedCat(null); setSelectedMajor(null) }
  const resetMajor = () => setSelectedMajor(null)

  const selectCat = (cat: Category) => {
    setSelectedCat(cat)
    setSelectedMajor(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const selectMajor = (m: Major) => {
    setSelectedMajor(m)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const totalMajors = categories.reduce((s, c) => s + c.majors.length, 0)

  return (
    <div>
      {/* 面包屑导航 */}
      <div style={{
        padding: '16px 28px', background: 'var(--paper)',
        borderBottom: '1px solid var(--border-light)',
        position: 'sticky', top: '52px', zIndex: 50,
        backdropFilter: 'blur(8px)',
      }}>
        <div className="container" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <Link to="/" style={{ color: 'var(--ink-lighter)', fontSize: '0.84rem' }}>首页</Link>
          <span style={{ color: 'var(--border)' }}>/</span>
          {!selectedCat ? (
            <span style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--ink)' }}>专业探索地图</span>
          ) : !selectedMajor ? (
            <>
              <button onClick={resetCat} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink-lighter)', fontSize: '0.84rem', fontFamily: 'inherit',
              }}>
                专业探索地图
              </button>
              <span style={{ color: 'var(--border)' }}>/</span>
              <span style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--accent)' }}>
                {selectedCat.icon} {selectedCat.name}
              </span>
            </>
          ) : (
            <>
              <button onClick={resetCat} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink-lighter)', fontSize: '0.84rem', fontFamily: 'inherit',
              }}>
                专业探索地图
              </button>
              <span style={{ color: 'var(--border)' }}>/</span>
              <button onClick={resetMajor} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--ink-lighter)', fontSize: '0.84rem', fontFamily: 'inherit',
              }}>
                {selectedCat.icon} {selectedCat.name}
              </button>
              <span style={{ color: 'var(--border)' }}>/</span>
              <span style={{ fontWeight: 600, fontSize: '0.84rem', color: 'var(--accent)' }}>
                {selectedMajor.icon} {selectedMajor.name}
              </span>
            </>
          )}
        </div>
      </div>

      <div className="page-header">
        <h1>🗺️ 专业探索地图</h1>
        <p>
          覆盖 {categories.length} 大学科门类、{totalMajors} 个代表性专业方向，
          包含专业简介、核心课程、就业方向和强校推荐
        </p>
      </div>

      <div className="container">
        {/* 提示卡片 */}
        <div className="card" style={{
          marginBottom: '28px', textAlign: 'center',
          background: 'linear-gradient(135deg, var(--green-light) 0%, var(--cream) 100%)',
          border: '1px solid var(--green-light)',
        }}>
          <p style={{ fontSize: '0.9rem', color: 'var(--ink)', lineHeight: 1.7 }}>
            👆 <strong>先选学科门类</strong> → 再探索具体专业 → 查看<strong>核心课程</strong>、<strong>就业方向</strong>和<strong>强校推荐</strong>
          </p>
          <p style={{ fontSize: '0.82rem', color: 'var(--ink-lighter)', marginTop: '6px' }}>
            每个专业都有详细的介绍，帮助你全面了解。还有困惑？去 <Link to="/qanda" style={{ fontWeight: 700, color: 'var(--accent)' }}>问答区</Link> 向智能大模型提问！
          </p>
        </div>

        {/* 阶段一：学科门类选择 */}
        {!selectedCat && (
          <>
            <div className="section-title">第一步：选择学科门类</div>
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))',
              gap: '14px', marginBottom: '40px',
            }}>
              {categories.map((cat, i) => (
                <div key={cat.name} className="card"
                  onClick={() => selectCat(cat)}
                  style={{
                    cursor: 'pointer', textAlign: 'center', padding: '32px 22px',
                    borderTop: `4px solid ${cat.color}`,
                    animation: `fadeIn 0.4s ${i * 50}ms both`,
                    transition: 'all 0.3s',
                  }}>
                  <div style={{ fontSize: '2.8rem', marginBottom: '12px' }}>{cat.icon}</div>
                  <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.15rem', fontWeight: 700, color: 'var(--ink)', marginBottom: '6px' }}>
                    {cat.name}
                  </h3>
                  <span className="tag" style={{ marginBottom: '8px' }}>{cat.subjects}</span>
                  <p style={{ color: 'var(--ink-light)', fontSize: '0.82rem', lineHeight: 1.5, marginTop: '8px' }}>
                    {cat.desc.slice(0, 55)}……
                  </p>
                  <div style={{ marginTop: '12px', color: 'var(--accent)', fontSize: '0.78rem', fontWeight: 600 }}>
                    包含 {cat.majors.length} 个专业方向 →
                  </div>
                </div>
              ))}
            </div>

            {/* 选科对照表 */}
            <div style={{ textAlign: 'center', marginBottom: '40px' }}>
              <button className="btn btn-outline"
                onClick={() => setExpandedCat(expandedCat ? null : 'subjects')}>
                📋 {expandedCat === 'subjects' ? '收起' : '查看'}新高考选科与专业对照
              </button>
              {expandedCat === 'subjects' && (
                <div className="card" style={{ marginTop: '16px', textAlign: 'left', padding: '28px 32px' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.88rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid var(--border)' }}>
                        <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--accent)', fontFamily: 'var(--font-serif)' }}>选科组合</th>
                        <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--accent)', fontFamily: 'var(--font-serif)' }}>可覆盖专业大类</th>
                        <th style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--accent)', fontFamily: 'var(--font-serif)' }}>推荐理由</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ['物理 + 化学', '几乎所有工科、理科、医学', '覆盖面最广，「物理+化学」是专业选择自由度最高的组合。'],
                        ['物理 + 化学 + 生物', '以上全部 + 医学临床类', '最全面的理科组合，适合目标明确的医学方向。'],
                        ['物理 + 地理', '测绘、地质、规划 + 部分工科', '地理在3+1+2省份赋分通常有优势。'],
                        ['历史 + 政治', '法学、新闻、哲学、教育学、公共管理', '典型"纯文科"组合，法学必选政治。'],
                        ['历史 + 政治 + 地理', '几乎所有文科专业', '文科生"王牌组合"，涵盖绝大部分文科专业。'],
                        ['不限选科', '经管类、语言类、设计类、部分文科', '有不少专业对选科无硬性要求，可按兴趣自由选。'],
                      ].map(([combo, cover, reason]) => (
                        <tr key={combo} style={{ borderBottom: '1px solid var(--border-light)' }}>
                          <td style={{ padding: '10px 14px', fontWeight: 700, color: 'var(--ink)' }}>{combo}</td>
                          <td style={{ padding: '10px 14px', color: 'var(--ink-light)', fontSize: '0.84rem' }}>{cover}</td>
                          <td style={{ padding: '10px 14px', color: 'var(--ink-lighter)', fontSize: '0.82rem' }}>{reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}

        {/* 阶段二：专业列表 */}
        {selectedCat && !selectedMajor && (
          <div>
            <button className="btn btn-outline" onClick={resetCat}
              style={{ marginBottom: '20px', padding: '10px 20px' }}>
              ← 返回学科门类选择
            </button>

            <div className="card" style={{
              marginBottom: '24px', padding: '28px 32px',
              borderLeft: `4px solid ${selectedCat.color}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '12px' }}>
                <span style={{ fontSize: '2.4rem' }}>{selectedCat.icon}</span>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.3rem', fontWeight: 700 }}>
                    {selectedCat.name}
                  </h2>
                  <div style={{ display: 'flex', gap: '8px', marginTop: '4px', flexWrap: 'wrap' }}>
                    <span className="tag">建议选科：{selectedCat.subjects}</span>
                    <span className="tag" style={{ background: selectedCat.color + '18', color: selectedCat.color }}>
                      {selectedCat.majors.length} 个专业方向
                    </span>
                  </div>
                </div>
              </div>
              <p style={{ color: 'var(--ink-light)', fontSize: '0.9rem', lineHeight: 1.7 }}>
                {selectedCat.desc}
              </p>
            </div>

            <div className="section-title" style={{ marginBottom: '18px' }}>
              选择你要了解的专业
            </div>

            {selectedCat.majors.map((m, i) => (
              <div key={m.name} className="card"
                onClick={() => selectMajor(m)}
                style={{
                  cursor: 'pointer',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  animation: `fadeIn 0.4s ${i * 50}ms both`,
                }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flex: 1 }}>
                  <div style={{
                    width: '52px', height: '52px', borderRadius: 'var(--radius-sm)',
                    background: selectedCat.color + '12',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '1.6rem', flexShrink: 0,
                  }}>
                    {m.icon}
                  </div>
                  <div>
                    <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1rem', fontWeight: 700, color: 'var(--ink)', marginBottom: '4px' }}>
                      {m.name}
                    </h3>
                    <p style={{ color: 'var(--ink-light)', fontSize: '0.84rem', lineHeight: 1.5 }}>
                      {m.desc}
                    </p>
                  </div>
                </div>
                <span style={{ color: 'var(--ink-lighter)', fontSize: '1.2rem', flexShrink: 0, marginLeft: '14px' }}>›</span>
              </div>
            ))}
          </div>
        )}

        {/* 阶段三：专业详情 */}
        {selectedMajor && selectedCat && (
          <div>
            <button className="btn btn-outline" onClick={resetMajor}
              style={{ marginBottom: '20px', padding: '10px 20px' }}>
              ← 返回{selectedCat.name}专业列表
            </button>

            <div className="card" style={{
              padding: '36px 32px',
              borderTop: `4px solid ${selectedCat.color}`,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
                <div style={{
                  width: '64px', height: '64px', borderRadius: 'var(--radius)',
                  background: selectedCat.color + '14',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '2.2rem',
                }}>
                  {selectedMajor.icon}
                </div>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.4rem', fontWeight: 700, color: 'var(--ink)', marginBottom: '4px' }}>
                    {selectedMajor.name}
                  </h2>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <span className="tag" style={{ background: selectedCat.color + '14', color: selectedCat.color, fontWeight: 600 }}>
                      {selectedCat.name}
                    </span>
                    <span className="tag">建议选科：{selectedCat.subjects}</span>
                  </div>
                </div>
              </div>

              {/* 专业简介 */}
              <div style={{ marginBottom: '28px' }}>
                <h3 style={{
                  fontFamily: 'var(--font-serif)', fontSize: '1.05rem', fontWeight: 700,
                  color: 'var(--accent)', marginBottom: '10px',
                  display: 'flex', alignItems: 'center', gap: '8px',
                }}>
                  <span style={{ width: '4px', height: '18px', background: selectedCat.color, borderRadius: '2px', display: 'inline-block' }} />
                  专业简介
                </h3>
                <p style={{ fontSize: '0.92rem', color: 'var(--ink)', lineHeight: 1.9, textAlign: 'justify' }}>
                  {selectedMajor.detail}
                </p>
              </div>

              {/* 核心课程 */}
              <div style={{ marginBottom: '28px' }}>
                <h3 style={{
                  fontFamily: 'var(--font-serif)', fontSize: '1.05rem', fontWeight: 700,
                  color: 'var(--accent)', marginBottom: '12px',
                  display: 'flex', alignItems: 'center', gap: '8px',
                }}>
                  <span style={{ width: '4px', height: '18px', background: selectedCat.color, borderRadius: '2px', display: 'inline-block' }} />
                  📚 核心课程
                </h3>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {selectedMajor.courses.map(c => (
                    <span key={c} className="tag" style={{
                      background: selectedCat.color + '0E',
                      color: 'var(--ink)',
                      fontSize: '0.82rem',
                      padding: '5px 14px',
                      border: '1px solid ' + selectedCat.color + '20',
                    }}>
                      {c}
                    </span>
                  ))}
                </div>
              </div>

              {/* 就业方向 */}
              <div style={{ marginBottom: '28px' }}>
                <h3 style={{
                  fontFamily: 'var(--font-serif)', fontSize: '1.05rem', fontWeight: 700,
                  color: 'var(--accent)', marginBottom: '12px',
                  display: 'flex', alignItems: 'center', gap: '8px',
                }}>
                  <span style={{ width: '4px', height: '18px', background: selectedCat.color, borderRadius: '2px', display: 'inline-block' }} />
                  🎯 就业方向
                </h3>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {selectedMajor.careers.map(c => (
                    <span key={c} className="tag" style={{
                      background: 'var(--accent-glow)',
                      color: 'var(--accent)',
                      fontWeight: 600,
                      fontSize: '0.82rem',
                      padding: '5px 14px',
                    }}>
                      {c}
                    </span>
                  ))}
                </div>
              </div>

              {/* 强校推荐 */}
              <div style={{ marginBottom: '10px' }}>
                <h3 style={{
                  fontFamily: 'var(--font-serif)', fontSize: '1.05rem', fontWeight: 700,
                  color: 'var(--accent)', marginBottom: '12px',
                  display: 'flex', alignItems: 'center', gap: '8px',
                }}>
                  <span style={{ width: '4px', height: '18px', background: selectedCat.color, borderRadius: '2px', display: 'inline-block' }} />
                  🏫 优势院校推荐
                  <span style={{ fontSize: '0.72rem', fontWeight: 500, color: 'var(--ink-lighter)', marginLeft: '4px' }}>
                    （教育部学科评估）
                  </span>
                </h3>
                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: '10px',
                }}>
                  {selectedMajor.topSchools.map(s => (
                    <div key={s.name} style={{
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '10px 16px',
                      background: 'var(--cream-dark)',
                      borderRadius: 'var(--radius-sm)',
                      borderLeft: '3px solid ' + (s.level === 'A+' ? selectedCat.color : 'var(--border)'),
                    }}>
                      <span style={{ fontSize: '0.86rem', fontWeight: 600, color: 'var(--ink)' }}>
                        {s.name}
                      </span>
                      <span style={{
                        fontSize: '0.72rem', fontWeight: 700,
                        color: s.level === 'A+' ? selectedCat.color : 'var(--ink-lighter)',
                        background: s.level === 'A+' ? selectedCat.color + '14' : 'transparent',
                        padding: '2px 8px', borderRadius: '4px',
                      }}>
                        {s.level}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="blockquote-decorated" style={{ marginTop: '28px', marginBottom: 0 }}>
                💡 <strong>还想了解更多？</strong>去
                <Link to="/qanda" style={{ fontWeight: 700, color: 'var(--accent)' }}> 问答区 </Link>
                搜索"{selectedMajor.name}"，看看有没有同学提过相关的问题，或自己提一个新的~
              </div>
            </div>

            {/* 同类快速跳转 */}
            <div style={{ marginTop: '24px' }}>
              <div className="section-title" style={{ fontSize: '0.95rem', marginBottom: '14px' }}>
                {selectedCat.name} · 其他专业方向
              </div>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {selectedCat.majors
                  .filter(m => m.name !== selectedMajor.name)
                  .map(m => (
                    <button key={m.name} className="btn btn-outline btn-sm"
                      onClick={() => selectMajor(m)}
                      style={{ borderRadius: '20px' }}>
                      {m.icon} {m.name}
                    </button>
                  ))}
              </div>
            </div>
          </div>
        )}

        <div style={{ textAlign: 'center', marginTop: '48px', paddingBottom: '48px' }}>
          <div className="ornament"><span>✦</span></div>
          <p style={{ color: 'var(--ink-lighter)', fontSize: '0.84rem', lineHeight: 1.7 }}>
            以上数据基于教育部最新学科评估和公开信息整理，仅供参考。
            <br />具体专业详情和招生计划请以各高校官方发布为准。
          </p>
        </div>
      </div>

      <style>{`@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  )
}
