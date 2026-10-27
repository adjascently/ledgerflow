import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const links = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/upload', label: 'Upload Statement' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/alerts', label: 'Alerts' },
]

export default function Nav() {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <nav className="nav">
      <div className="nav-logo">Finance Tracker</div>
      <div className="nav-user">{user?.email}</div>
      <ul className="nav-links">
        {links.map((l) => (
          <li key={l.to}>
            <NavLink to={l.to} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
              {l.label}
            </NavLink>
          </li>
        ))}
      </ul>
      <button className="nav-signout" onClick={handleSignOut}>Sign out</button>
    </nav>
  )
}
