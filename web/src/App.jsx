import Anillos from './Anillos'
import Chat from './Chat'
import { useRosario } from './useRosario'
import './estilos.css'

export default function App() {
  const rosario = useRosario()
  return (
    <main>
      <Anillos estado={rosario.estado} />
      <Chat {...rosario} />
    </main>
  )
}