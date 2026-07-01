import { useEffect, useRef } from 'react'
import { runsApi } from '@/api/runs'
import type { AgentEvent } from '@/api/types'
import { useRunStore } from '@/store/runStore'

const MAX_RETRIES = 10
const BASE_DELAY_MS = 1000

export function useAgentEventStream(runId: number | null) {
  const applyEvent = useRunStore((s) => s.applyEvent)
  const retriesRef = useRef(0)

  useEffect(() => {
    if (!runId) return

    let es: EventSource | null = null
    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      if (cancelled) return
      es = new EventSource(runsApi.eventsUrl(runId))

      const handleMessage = (ev: MessageEvent) => {
        try {
          const event = JSON.parse(ev.data) as AgentEvent
          applyEvent(event)
          retriesRef.current = 0
        } catch {
          // ignore malformed events
        }
      }

      es.onmessage = handleMessage
      es.addEventListener('job_updated', handleMessage)
      es.addEventListener('counters_updated', handleMessage)
      es.addEventListener('run_completed', handleMessage)
      es.addEventListener('run_interrupted', handleMessage)

      es.onerror = () => {
        es?.close()
        if (cancelled) return
        if (retriesRef.current >= MAX_RETRIES) return
        const delay = BASE_DELAY_MS * 2 ** retriesRef.current
        retriesRef.current += 1
        retryTimer = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimer) clearTimeout(retryTimer)
      es?.close()
    }
  }, [runId, applyEvent])
}
