import { useCallback, useEffect, useRef, useState } from 'react'

const CLAVE_VOZ = 'rosario_voz'

export function useVoz(sesionId) {
  const [activa, setActiva] = useState(() => {
    try {
      return localStorage.getItem(CLAVE_VOZ) === 'si'
    } catch {
      return false
    }
  })
  const [hablando, setHablando] = useState(false)
  const [aviso, setAviso] = useState(null)
  const audioRef = useRef(null)
  // Cada pedido lleva su numero: si llega tarde uno viejo, se descarta.
  const turnoRef = useRef(0)

  function frenar() {
    turnoRef.current += 1
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      URL.revokeObjectURL(audio.src) // libera el audio anterior de la memoria
      audioRef.current = null
    }
    setHablando(false)
  }

  // Si el usuario cierra la pestaña mientras habla, el audio se corta.
  useEffect(() => () => frenar(), [])

    const hablar = useCallback(
    async (texto) => {
      if (!activa || !texto) return
      frenar()
      setAviso(null)
      const turno = turnoRef.current
      setHablando(true)

      try {
        const respuesta = await fetch('/voz', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sesion_id: sesionId, texto }),
        })
        if (respuesta.status === 429) {
          const datos = await respuesta.json()
          if (turno === turnoRef.current) setAviso(datos.detail)
          throw new Error('limite')
        }
        if (!respuesta.ok) throw new Error('sin audio')

        const blob = await respuesta.blob()
        // Mientras se generaba el audio el usuario pudo apagar la voz o
        // preguntar otra cosa: si el turno cambio, este audio ya no va.
        if (turno !== turnoRef.current) return

        const audio = new Audio(URL.createObjectURL(blob))
        audioRef.current = audio
        audio.onended = () => setHablando(false)
        audio.onerror = () => setHablando(false)
        await audio.play()
      } catch {
        // Sin audio, la respuesta igual se lee en pantalla.
        if (turno === turnoRef.current) setHablando(false)
      }
    },
    [activa, sesionId],
  )

  const alternar = useCallback(() => {
    setActiva((antes) => {
      const ahora = !antes
      try {
        localStorage.setItem(CLAVE_VOZ, ahora ? 'si' : 'no')
      } catch {
        // Sin almacenamiento, la eleccion dura lo que la pestaña.
      }
      if (!ahora) frenar()
      return ahora
    })
  }, [])

  // El audio lo genera el servidor: no depende de las voces del navegador.
  return { soportada: true, activa, hablando, aviso, hablar, alternar }
}