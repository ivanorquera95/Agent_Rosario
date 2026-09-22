import { useEffect, useState } from 'react'

// Hora de Rosario, sin importar la zona horaria de quien abra la pagina.
const FORMATO = new Intl.DateTimeFormat('es-AR', {
  timeZone: 'America/Argentina/Buenos_Aires',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export default function Reloj() {
  const [ahora, setAhora] = useState(() => new Date())

  useEffect(() => {
    const intervalo = setInterval(() => setAhora(new Date()), 1000)
    // Limpieza del efecto: si el componente desaparece, el reloj se frena.
    return () => clearInterval(intervalo)
  }, [])

  return <time className="reloj">{FORMATO.format(ahora)}</time>
}