import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  ReactNode,
} from 'react'
import type { Job } from '../api'

interface WsMessage {
  type: string
  job_id?: string
  [key: string]: unknown
}

interface WsCtx {
  jobs: Record<string, Job>
  connected: boolean
}

const WsContext = createContext<WsCtx>({ jobs: {}, connected: false })

export function WsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Record<string, Job>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(`ws://${location.host}/ws/progress`)
      wsRef.current = ws

      ws.onopen = () => setConnected(true)
      ws.onclose = () => {
        setConnected(false)
        setTimeout(connect, 3000) // auto-reconnect
      }
      ws.onerror = () => ws.close()

      ws.onmessage = (evt) => {
        const msg: WsMessage = JSON.parse(evt.data)
        if (msg.type === 'snapshot') {
          const snap = (msg.jobs as Job[]) ?? []
          setJobs(Object.fromEntries(snap.map((j) => [j.id, j])))
        } else if (msg.job_id) {
          setJobs((prev) => ({
            ...prev,
            [msg.job_id!]: { ...(prev[msg.job_id!] ?? {}), ...msg } as Job,
          }))
        }
      }
    }
    connect()
    return () => wsRef.current?.close()
  }, [])

  return <WsContext.Provider value={{ jobs, connected }}>{children}</WsContext.Provider>
}

export function useWs() {
  return useContext(WsContext)
}
