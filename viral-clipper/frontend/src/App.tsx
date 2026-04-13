import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Scissors, LayoutGrid, MessageSquare, TrendingUp, History, Zap } from 'lucide-react'
import clsx from 'clsx'
import Home from './pages/Home'
import Results from './pages/Results'
import Review from './pages/Review'
import Analytics from './pages/Analytics'
import HistoryPage from './pages/HistoryPage'
import { WsProvider } from './hooks/useWs'

const NAV = [
  { to: '/', label: 'Clip', icon: Scissors, end: true },
  { to: '/results', label: 'Clips', icon: LayoutGrid },
  { to: '/review', label: 'Review', icon: MessageSquare },
  { to: '/analytics', label: 'Analytics', icon: TrendingUp },
  { to: '/history', label: 'History', icon: History },
]

export default function App() {
  return (
    <WsProvider>
      <BrowserRouter>
        <div className="min-h-screen flex bg-bg">
          {/* Sidebar */}
          <aside className="w-16 md:w-56 flex-shrink-0 bg-surface border-r border-border flex flex-col">
            {/* Logo */}
            <div className="h-16 flex items-center justify-center md:justify-start md:px-5 border-b border-border">
              <Zap className="text-neon w-6 h-6 flex-shrink-0" />
              <span className="hidden md:block ml-2 font-mono font-bold text-neon text-lg tracking-tight">
                ViralClipper
              </span>
            </div>

            {/* Nav links */}
            <nav className="flex-1 py-4">
              {NAV.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center justify-center md:justify-start gap-3',
                      'px-3 md:px-5 py-3 mx-2 rounded-lg transition-all duration-150 text-sm font-medium',
                      isActive
                        ? 'bg-neon/10 text-neon border border-neon/30 shadow-neon-sm'
                        : 'text-muted hover:text-white hover:bg-white/5'
                    )
                  }
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  <span className="hidden md:block">{label}</span>
                </NavLink>
              ))}
            </nav>

            <div className="p-4 hidden md:block text-xs text-muted border-t border-border">
              v1.0.0
            </div>
          </aside>

          {/* Main content */}
          <main className="flex-1 overflow-auto">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/results" element={<Results />} />
              <Route path="/review" element={<Review />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/history" element={<HistoryPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </WsProvider>
  )
}
