import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import './App.css';
import GitHubAnalyzer from './components/GitHubAnalyzer';
import AnalysisDashboard from './components/AnalysisDashboard';
import Header from './components/Header';

function App() {
  return (
    <Router>
      <div className="App">
        <Header />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<GitHubAnalyzer />} />
            <Route path="/analysis/:analysisId" element={<AnalysisDashboard />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
