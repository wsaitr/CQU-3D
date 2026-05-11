import React, { useState } from 'react';
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowRight, Mail, Lock, User } from 'lucide-react';
import logoSvg from '../assets/logo.svg';
import API from '../services/api';

const Auth = ({ setIsAuth }) => {
  const [isLogin, setIsLogin] = useState(true);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isLogin) {
        await API.login(formData.username, formData.password);
        setIsAuth(true);
      } else {
        await API.register(formData.username, formData.email, formData.password);
        setIsLogin(true);
        setError('注册成功，请登录');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'radial-gradient(circle at center, #1a1a1a 0%, #000000 100%)',
      padding: '2rem'
    }}>
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-card"
        style={{
          width: '100%',
          maxWidth: '450px',
          padding: '3rem',
          position: 'relative',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
          <motion.div
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: 'spring', damping: 10 }}
            style={{
              width: '64px',
              height: '64px',
              background: 'linear-gradient(135deg, #6366f1, #a855f7)',
              borderRadius: '20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 1.5rem',
              boxShadow: '0 0 30px rgba(99, 102, 241, 0.4)'
            }}
          >
            <img src={logoSvg} alt="Logo" style={{ width: 36, height: 36, filter: 'brightness(2)' }} />
          </motion.div>
          <h2 style={{ fontSize: '2rem', fontWeight: '800', marginBottom: '0.5rem' }}>
            {isLogin ? '欢迎回来' : '开启能量'}
          </h2>
          <p style={{ color: 'var(--text-muted)' }}>
            {isLogin ? '登录以访问您的工程控制台' : '创建账号以开始您的加工任务'}
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          {error && (
            <div style={{
              background: 'rgba(230, 0, 8, 0.1)',
              border: '1px solid var(--primary)',
              color: 'var(--primary)',
              padding: '1rem',
              borderRadius: 'var(--radius-md)',
              marginBottom: '1.5rem',
              fontSize: '0.9rem'
            }}>
              {error}
            </div>
          )}

          <div className="input-group">
            <label className="input-label">用户名</label>
            <div style={{ position: 'relative' }}>
              <User size={18} style={{ position: 'absolute', left: '1.2rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input 
                type="text" 
                className="nanfu-input" 
                style={{ paddingLeft: '3.5rem' }}
                placeholder="您的用户名"
                required
                value={formData.username}
                onChange={(e) => setFormData({...formData, username: e.target.value})}
              />
            </div>
          </div>

          {!isLogin && (
            <div className="input-group">
              <label className="input-label">电子邮箱</label>
              <div style={{ position: 'relative' }}>
                <Mail size={18} style={{ position: 'absolute', left: '1.2rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                <input 
                  type="email" 
                  className="nanfu-input" 
                  style={{ paddingLeft: '3.5rem' }}
                  placeholder="name@example.com"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({...formData, email: e.target.value})}
                />
              </div>
            </div>
          )}

          <div className="input-group">
            <label className="input-label">访问密码</label>
            <div style={{ position: 'relative' }}>
              <Lock size={18} style={{ position: 'absolute', left: '1.2rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input 
                type="password" 
                className="nanfu-input" 
                style={{ paddingLeft: '3.5rem' }}
                placeholder="••••••••"
                required
                value={formData.password}
                onChange={(e) => setFormData({...formData, password: e.target.value})}
              />
            </div>
          </div>

          <button 
            type="submit" 
            className="btn-primary" 
            style={{ width: '100%', justifyContent: 'center', marginTop: '1rem', height: '3.5rem' }}
            disabled={loading}
          >
            {loading ? '处理中...' : (isLogin ? '立即登录' : '注册账号')}
            {!loading && <ArrowRight size={20} />}
          </button>
        </form>

        <div style={{ marginTop: '2rem', textAlign: 'center', fontSize: '0.9rem' }}>
          <span style={{ color: 'var(--text-muted)' }}>
            {isLogin ? '没有账号?' : '已有账号?'}
          </span>
          <button 
            onClick={() => { setIsLogin(!isLogin); setError(''); }}
            style={{ 
              background: 'none', 
              border: 'none', 
              color: 'var(--primary)', 
              fontWeight: '600', 
              marginLeft: '0.5rem', 
              cursor: 'pointer' 
            }}
          >
            {isLogin ? '去注册' : '去登录'}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default Auth;
