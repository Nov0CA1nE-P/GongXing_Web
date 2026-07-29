import { useEffect, useState } from 'react'
import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import Home from './pages/Home'
import Courseware from './pages/Courseware'
import Guestbook from './pages/Guestbook'
import QandA from './pages/QandA'
import Explore from './pages/Explore'
import AITest from './pages/AITest'
import Contact from './pages/Contact'
import Admin from './pages/Admin'
import Privacy from './pages/Privacy'
import NotFound from './pages/NotFound'

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
          <Route path="/contact" element={<Contact />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <BackToTop />
      <footer className="footer">
        <p>
          躬行启杭专业科普体验夏令营 © 2026
          {' | '}主办：北京科技大学
          {' | '}协办：浙江省杭州学军中学
          {' | '}<a href="/privacy">隐私说明</a>
        </p>
      </footer>
    </>
  )
}

export default App
