import { useEffect, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Courseware from './pages/Courseware'
import Guestbook from './pages/Guestbook'
import QandA from './pages/QandA'
import Explore from './pages/Explore'
import AITest from './pages/AITest'
import Scores from './pages/Scores'
import Contact from './pages/Contact'
import Admin from './pages/Admin'

function BackToTop() {
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 400)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  if (!visible) return null
  return (
    <button
      onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
      style={{
        position: 'fixed', bottom: '28px', right: '28px', zIndex: 999,
        width: '44px', height: '44px', borderRadius: '50%',
        background: 'var(--accent)', color: 'white', border: 'none',
        cursor: 'pointer', fontSize: '1.2rem',
        boxShadow: '0 4px 16px rgba(212,116,58,0.35)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: 'all 0.3s',
      }}
      title="回到顶部"
    >
      ↑
    </button>
  )
}

function App() {
  return (
    <>
      <Navbar />
      <main style={{ minHeight: 'calc(100vh - 140px)' }}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/courseware" element={<Courseware />} />
          <Route path="/guestbook" element={<Guestbook />} />
          <Route path="/qanda" element={<QandA />} />
          <Route path="/explore" element={<Explore />} />
          <Route path="/aitest" element={<AITest />} />
          <Route path="/scores" element={<Scores />} />
          <Route path="/contact" element={<Contact />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </main>
      <BackToTop />
      <footer className="footer">
        <p>北京科技大学 躬行启杭专业科普体验实践团 © 2026 | 学军中学紫金港校区</p>
      </footer>
    </>
  )
}

export default App
