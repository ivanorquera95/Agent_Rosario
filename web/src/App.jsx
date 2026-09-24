import Anillos from './Anillos'
import Chat from './Chat'
import Reloj from './Reloj'
import { useRosario } from './useRosario'
import './estilos.css'

const TEXTO_INDICADOR = {
  reposo: 'EN ESPERA',
  pensando: 'PENSANDO',
  hablando: 'HABLANDO',
}

export default function App() {
  const rosario = useRosario()
  // Mientras la voz suena, los anillos siguen latiendo aunque el texto ya termino.
  const estadoVisual = rosario.voz.hablando ? 'hablando' : rosario.estado

  return (
    <main className="app">
      <header className="barra">
        <span>ROSARIO VIVO</span>
        <Reloj />
      </header>

      <section className="nucleo-zona">
        <Anillos estado={estadoVisual} />
        {/* aria-hidden: el estado ya lo anuncia el texto para lectores de Chat.jsx */}
        <p className={`indicador ${estadoVisual}`} aria-hidden="true">
          <span className="nombre">ROSARIO</span>
          <span className="punto" />
          {TEXTO_INDICADOR[estadoVisual]}
        </p>
      </section>

      <Chat {...rosario} />
    </main>
  )
}