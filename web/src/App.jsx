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
  return (
    <main className="app">
      <header className="barra">
        <span>ROSARIO VIVO</span>
        <Reloj />
      </header>

      <section className="nucleo-zona">
        <Anillos estado={rosario.estado} />
        {/* aria-hidden: el estado ya lo anuncia el texto para lectores de Chat.jsx */}
        <p className={`indicador ${rosario.estado}`} aria-hidden="true">
          <span className="punto" />
          {TEXTO_INDICADOR[rosario.estado]}
        </p>
      </section>

      <Chat {...rosario} />
    </main>
  )
}