import { createRoot } from 'react-dom/client'
import App from './App'
// 글꼴은 모두 빌드에 포함한다 (외부 CDN 없음). Pretendard는 글자 묶음별로 나뉘어 화면에 쓰인 묶음만 받는다
import 'pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css'
import '@fontsource/jetbrains-mono/latin-600.css'
import '@fontsource/jetbrains-mono/latin-700.css'
import './styles/fonts.css'
import './style.css'
createRoot(document.getElementById('root')!).render(<App />)
