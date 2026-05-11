import React from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { LogOut, LayoutGrid } from 'lucide-react';
import logoSvg from '../assets/logo.svg';
import API from '../services/api';

const Navbar = ({ setIsAuth }) => {
  const navigate = useNavigate();

  const handleLogout = () => {
    API.logout();
    setIsAuth(false);
    navigate('/auth');
  };

  return (
    <nav style={{
      position: 'sticky',
      top: 0,
      zIndex: 100,
      background: 'rgba(0,0,0,0.8)',
      backdropFilter: 'blur(10px)',
      borderBottom: '1px solid var(--glass-border)',
      padding: '1rem 0'
    }}>
      <div className="nanfu-container" style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <Link to="/" style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '0.8rem',
          fontSize: '1.5rem',
          fontWeight: '800',
          letterSpacing: '-1px'
        }}>
          <img src={logoSvg} alt="Logo" style={{ width: 32, height: 32 }} />
          <span>3D <span style={{ color: '#a855f7' }}>Studio</span></span>
        </Link>

        <div style={{ display: 'flex', alignItems: 'center', gap: '2rem' }}>
          <Link to="/" style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '0.5rem',
            color: 'var(--text-muted)',
            transition: 'var(--transition)'
          }} className="nav-link">
            <LayoutGrid size={20} />
            <span>控制台</span>
          </Link>
          
          <button 
            onClick={handleLogout}
            className="btn-outline" 
            style={{ 
              padding: '0.5rem 1.2rem', 
              fontSize: '0.9rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}
          >
            <LogOut size={16} />
            退出
          </button>
        </div>
      </div>
      
      <style>{`
        .nav-link:hover {
          color: white !important;
        }
      `}</style>
    </nav>
  );
};

export default Navbar;
