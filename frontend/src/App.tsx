import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import Assessments from './pages/Assessments'
import AssessmentDetail from './pages/AssessmentDetail'
import Findings from './pages/Findings'
import FindingDetail from './pages/FindingDetail'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Overview />} />
        <Route path="/assessments" element={<Assessments />} />
        <Route path="/assessments/:id" element={<AssessmentDetail />} />
        <Route path="/findings" element={<Findings />} />
        <Route path="/findings/:id" element={<FindingDetail />} />
      </Route>
    </Routes>
  )
}
