import Chat from './Chat'
import { useRosario } from './useRosario'

export default function App() {
  const rosario = useRosario()
  return (
    <main>
      <h1>Rosario</h1>
      <Chat {...rosario} />
    </main>
  )
}