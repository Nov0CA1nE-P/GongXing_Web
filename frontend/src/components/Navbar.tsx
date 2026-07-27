import { useState } from 'react'
import { NavLink } from 'react-router-dom'

export default function Navbar() {
  const [open, setOpen] = useState(false)

  return (
    <nav className="navbar">
      <div className="container">
        <NavLink to="/" className="logo" onClick={() => setOpen(false)}>
          躬行启杭
        </NavLink>

        <button className="menu-btn" onClick={() => setOpen(!open)} aria-label="菜单">
          <span className={`ham ${open ? 'open' : ''}`} />
          <span className={`ham ${open ? 'open' : ''}`} />
        </button>

        <ul className={`nav-links ${open ? 'open' : ''}`}>
          <li><NavLink to="/courseware" onClick={() => setOpen(false)}>课件</NavLink></li>
          <li><NavLink to="/guestbook" onClick={() => setOpen(false)}>留言</NavLink></li>
          <li><NavLink to="/qanda" onClick={() => setOpen(false)}>问答</NavLink></li>
          <li><NavLink to="/contact" onClick={() => setOpen(false)}>联系</NavLink></li>
        </ul>
      </div>

      <style>{`
        .menu-btn {
          display: none; flex-direction: column; gap: 4px;
          background: none; border: none; cursor: pointer; padding: 6px; z-index: 101;
        }
        .ham {
          display: block; width: 18px; height: 2px;
          background: var(--ink); border-radius: 2px; transition: all 0.3s;
        }
        .ham.open:nth-child(1) { transform: rotate(45deg) translate(4px, 4px); }
        .ham.open:nth-child(2) { transform: rotate(-45deg) translate(4px, -4px); }

        @media (max-width: 640px) {
          .menu-btn { display: flex; }
          .nav-links {
            display: none !important;
            position: fixed; top: 52px; left: 0; right: 0;
            background: rgba(254,249,240,0.96);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            flex-direction: column;
            padding: 20px 28px;
            border-bottom: 1px solid var(--border-light);
            box-shadow: var(--shadow);
          }
          .nav-links.open { display: flex !important; }
        }
      `}</style>
    </nav>
  )
}
