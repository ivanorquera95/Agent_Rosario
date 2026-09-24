import { useVoz } from './useVoz'
import { useEffect, useState } from 'react'


const CLAVE_SESION = 'rosario_sesion_id'

function obtenerSesionId() {
  try {
    let id = localStorage.getItem(CLAVE_SESION)
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem(CLAVE_SESION, id)
    }
    return id
  } catch {
    // Navegacion privada o almacenamiento bloqueado: la charla dura lo que la pestaña.
    return crypto.randomUUID()
  }
}

// Lee el stream SSE que manda FastAPI. Cada evento viene como "data: {json}"
// seguido de una linea en blanco, y un pedazo de red puede cortar un evento a
// la mitad: lo incompleto queda en 'pendiente' hasta que llega el resto.
async function leerEventos(respuesta, alRecibir) {
  const lector = respuesta.body.pipeThrough(new TextDecoderStream()).getReader()
  let pendiente = ''
  while (true) {
    const { value, done } = await lector.read()
    if (done) break
    pendiente += value
    const bloques = pendiente.split('\n\n')
    pendiente = bloques.pop()
    for (const bloque of bloques) {
      if (bloque.startsWith('data: ')) alRecibir(JSON.parse(bloque.slice(6)))
    }
  }
}

export function useRosario() {
  // useState: un dato que, cuando cambia, hace que React vuelva a dibujar la pantalla.
  const [sesionId, setSesionId] = useState(obtenerSesionId)
  const [mensajes, setMensajes] = useState([])
  const [estado, setEstado] = useState('reposo') // reposo | pensando | hablando
  const [error, setError] = useState(null)
  const voz = useVoz(sesionId)

  // useEffect: codigo que corre cuando algo cambia. Aca, al abrir la pagina
  // o al cambiar de conversacion, se trae lo que el servidor recuerda.
    // Al abrir la pagina o al cambiar de conversacion: lo que el servidor recuerda.
  useEffect(() => {
    pedirHistorial(sesionId).then(setMensajes)
  }, [sesionId])

  // Al volver a esta pestaña: si en otra se empezo una conversacion nueva, se
  // toma ese id; si no, se vuelve a pedir el historial por si hubo mensajes nuevos.
  useEffect(() => {
    function alVolver() {
      // Con una respuesta en curso no se toca nada: todavia no esta guardada
      // en el servidor y pisaria lo que se esta escribiendo en pantalla.
      if (document.visibilityState !== 'visible' || estado !== 'reposo') return
      const idGuardado = leerIdGuardado()
      if (idGuardado && idGuardado !== sesionId) {
        setSesionId(idGuardado) // dispara el efecto de arriba
      } else {
        pedirHistorial(sesionId).then(setMensajes)
      }
    }
    document.addEventListener('visibilitychange', alVolver)
    // Lo que devuelve un efecto es su limpieza: sin esto, cada cambio de
    // estado agregaria un escuchador mas sin sacar el anterior.
    return () => document.removeEventListener('visibilitychange', alVolver)
  }, [sesionId, estado])

  // Cambia solo el ultimo mensaje, que es la respuesta que se esta escribiendo.
  // Se usa la forma setMensajes(prev => ...) porque los eventos llegan muy
  // seguidos: leer 'mensajes' directo daria una version vieja de la lista.
  function actualizarUltima(cambiar) {
    setMensajes((prev) => {
      const copia = [...prev]
      const ultima = copia[copia.length - 1]
      copia[copia.length - 1] = { ...ultima, contenido: cambiar(ultima.contenido) }
      return copia
    })
  }

  async function enviar(texto) {
    if (!texto.trim() || estado !== 'reposo') return
    setError(null)
    // La pregunta y una respuesta vacia que se va llenando con el stream.
    setMensajes((prev) => [
      ...prev,
      { rol: 'user', contenido: texto },
      { rol: 'assistant', contenido: '' },
    ])
    setEstado('pensando')

    try {
      const respuesta = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sesion_id: sesionId, mensaje: texto }),
      })
      if (respuesta.status === 409) throw new Error('Estoy respondiendo en otra pestaña. Esperá un momento.')
      if (!respuesta.ok) throw new Error('No pude enviar el mensaje.')

      await leerEventos(respuesta, (evento) => {
        if (evento.tipo === 'herramienta') {
          setEstado('pensando')
        } else if (evento.tipo === 'texto') {
          setEstado('hablando')
          actualizarUltima((c) => c + evento.contenido)
        } else if (evento.tipo === 'fin') {
          actualizarUltima(() => evento.texto_limpio)
          voz.hablar(evento.voz)
        } else if (evento.tipo === 'error') {
          throw new Error(evento.mensaje)
        }
      })
    } catch (e) {
      setError(e.message)
      // El servidor no guardo este turno: se saca de la pantalla para que
      // lo que se ve coincida con lo que Rosario recuerda.
      setMensajes((prev) => prev.slice(0, -2))
    } finally {
      setEstado('reposo')
    }
  }

  function nuevaConversacion() {
    const id = crypto.randomUUID()
    try {
      localStorage.setItem(CLAVE_SESION, id)
    } catch {
      // Sin almacenamiento, la conversacion nueva dura lo que la pestaña.
    }
    setSesionId(id)
    setMensajes([])
    setError(null)
  }

  return { sesionId, mensajes, estado, error, enviar, nuevaConversacion, voz }
}

function leerIdGuardado() {
  try {
    return localStorage.getItem(CLAVE_SESION)
  } catch {
    return null
  }
}

async function pedirHistorial(id) {
  try {
    const r = await fetch('/historial', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sesion_id: id }),
    })
    return r.ok ? (await r.json()).mensajes : []
  } catch {
    return []
  }
}