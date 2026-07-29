import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { categories, type Category, type Major } from '../data/majors'

export default function Explore() {
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null)
  const [selectedMajor, setSelectedMajor] = useState<Major | null>(null)
  const [search, setSearch] = useState('')

  const majors = useMemo(() => {
    if (!selectedCategory) return []
    const keyword = search.trim().toLowerCase()
    if (!keyword) return selectedCategory.majors
    return selectedCategory.majors.filter(major =>
      major.name.toLowerCase().includes(keyword)
      || major.courses.some(course => course.toLowerCase().includes(keyword))
      || major.careers.some(career => career.toLowerCase().includes(keyword)),
    )
  }, [search, selectedCategory])

  const chooseCategory = (category: Category) => {
    setSelectedCategory(category)
    setSelectedMajor(null)
    setSearch('')
  }

  return (
    <div>
      <div className="page-header">
        <h1>🗺️ 专业探索</h1>
        <p>浏览部分专业示例，了解可能涉及的课程和职业方向</p>
      </div>

      <div className="container">
        <div className="blockquote-decorated" style={{ marginBottom: '28px', fontSize: '0.86rem' }}>
          当前分类是网站为浏览体验整理的主题分类，不等同于教育部官方学科门类，也不覆盖全部本科专业。
          课程和职业方向均为示例，不构成选科、报考、就业或院校推荐。
        </div>

        {!selectedCategory && (
          <>
            <div className="section-title">选择感兴趣的主题</div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
              gap: '14px',
            }}>
              {categories.map(category => (
                <button
                  key={category.name}
                  className="card"
                  onClick={() => chooseCategory(category)}
                  style={{
                    border: '1px solid var(--border-light)',
                    cursor: 'pointer',
                    textAlign: 'left',
                    fontFamily: 'inherit',
                    color: 'inherit',
                  }}
                >
                  <div style={{ fontSize: '2rem', marginBottom: '12px' }}>{category.icon}</div>
                  <h2 style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: '1.08rem',
                    marginBottom: '6px',
                  }}>
                    {category.name}
                  </h2>
                  <p style={{ color: 'var(--ink-lighter)', fontSize: '0.8rem' }}>
                    {category.majors.length} 个专业示例
                  </p>
                </button>
              ))}
            </div>
          </>
        )}

        {selectedCategory && !selectedMajor && (
          <>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelectedCategory(null)}>
              ← 返回主题分类
            </button>
            <div style={{ margin: '22px 0' }}>
              <div className="section-title">
                {selectedCategory.icon} {selectedCategory.name}
              </div>
              <input
                value={search}
                onChange={event => setSearch(event.target.value)}
                placeholder="搜索专业、课程或职业方向"
                style={{ width: '100%', maxWidth: '420px' }}
              />
            </div>
            {majors.length === 0 ? (
              <div className="empty"><p>没有匹配的专业示例</p></div>
            ) : (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                gap: '14px',
              }}>
                {majors.map(major => (
                  <button
                    key={major.name}
                    className="card"
                    onClick={() => setSelectedMajor(major)}
                    style={{
                      border: '1px solid var(--border-light)',
                      cursor: 'pointer',
                      textAlign: 'left',
                      fontFamily: 'inherit',
                      color: 'inherit',
                    }}
                  >
                    <div style={{ fontSize: '1.8rem', marginBottom: '10px' }}>{major.icon}</div>
                    <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1rem' }}>
                      {major.name}
                    </h2>
                    <p style={{ color: 'var(--ink-lighter)', fontSize: '0.78rem', marginTop: '8px' }}>
                      查看课程与职业方向示例
                    </p>
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {selectedCategory && selectedMajor && (
          <>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelectedMajor(null)}>
              ← 返回{selectedCategory.name}
            </button>
            <div className="card" style={{ marginTop: '20px', padding: '32px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '28px' }}>
                <span style={{ fontSize: '2.4rem' }}>{selectedMajor.icon}</span>
                <div>
                  <span className="tag">{selectedCategory.name}</span>
                  <h1 style={{
                    fontFamily: 'var(--font-serif)',
                    fontSize: '1.45rem',
                    marginTop: '6px',
                  }}>
                    {selectedMajor.name}
                  </h1>
                </div>
              </div>

              <section style={{ marginBottom: '28px' }}>
                <h2 className="section-title">可能涉及的课程</h2>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {selectedMajor.courses.map(course => (
                    <span key={course} className="tag">{course}</span>
                  ))}
                </div>
              </section>

              <section>
                <h2 className="section-title">职业方向示例</h2>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {selectedMajor.careers.map(career => (
                    <span key={career} className="tag">{career}</span>
                  ))}
                </div>
              </section>

              <p style={{ marginTop: '28px', color: 'var(--ink-lighter)', fontSize: '0.82rem' }}>
                实际课程设置和培养方向以高校官方信息为准。还有疑问，可以前往
                {' '}<Link to="/qanda">专业问答</Link>。
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
