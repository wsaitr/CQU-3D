import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Auth from './pages/Auth';
import Dashboard from './pages/Dashboard';
import ProjectDetail from './pages/ProjectDetail';
import PLYViewer from './pages/PLYViewer';
import Navbar from './components/Navbar';

function App() {
  const [isAuth, setIsAuth] = useState(Boolean(localStorage.getItem('access_token')));

  useEffect(() => {
    const handleUnauthorized = () => {
      setIsAuth(false);
    };
    window.addEventListener('unauthorized', handleUnauthorized);
    return () => window.removeEventListener('unauthorized', handleUnauthorized);
  }, []);

  return (
    <Router>
      <div className="app">
        {isAuth && <Navbar setIsAuth={setIsAuth} />}
        <Routes>
          <Route 
            path="/auth" 
            element={!isAuth ? <Auth setIsAuth={setIsAuth} /> : <Navigate to="/" />} 
          />
          <Route 
            path="/" 
            element={isAuth ? <Dashboard /> : <Navigate to="/auth" />} 
          />
          <Route 
            path="/project/:id" 
            element={isAuth ? <ProjectDetail /> : <Navigate to="/auth" />} 
          />
          <Route 
            path="/project/:projectId/ply-viewer" 
            element={isAuth ? <PLYViewer /> : <Navigate to="/auth" />} 
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
