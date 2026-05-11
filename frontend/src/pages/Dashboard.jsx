import React, { useState, useEffect } from 'react';
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, Folder, Calendar, Trash2, ArrowRight, Activity } from 'lucide-react';
import { Link } from 'react-router-dom';
import API from '../services/api';

const Dashboard = () => {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [newProject, setNewProject] = useState({ name: '', description: '' });

  useEffect(() => {
    fetchProjects();
  }, []);

  const fetchProjects = async () => {
    try {
      const data = await API.getProjects();
      setProjects(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    try {
      await API.createProject(newProject.name, newProject.description);
      setShowModal(false);
      setNewProject({ name: '', description: '' });
      fetchProjects();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleDelete = async (e, id) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm('确定要删除这个工程吗?')) return;
    try {
      await API.deleteProject(id);
      fetchProjects();
    } catch (err) {
      alert(err.message);
    }
  };

  return (
    <div className="nanfu-container" style={{ paddingTop: '4rem', paddingBottom: '6rem' }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'flex-end',
        marginBottom: '4rem'
      }}>
        <div>
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.8rem', 
              color: 'var(--primary)',
              fontWeight: '600',
              marginBottom: '1rem'
            }}
          >
            <Activity size={20} />
            <span>PROJECT MANAGEMENT</span>
          </motion.div>
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ fontSize: '3.5rem', fontWeight: '800', letterSpacing: '-2px', lineHeight: 1 }}
          >
            我的控制台
          </motion.h1>
        </div>

        <motion.button 
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          className="btn-primary"
          onClick={() => setShowModal(true)}
          style={{ height: '3.5rem', padding: '0 2rem' }}
        >
          <Plus size={24} />
          新建工程
        </motion.button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '5rem', color: 'var(--text-muted)' }}>
          加载中...
        </div>
      ) : projects.length === 0 ? (
        <div className="glass-card" style={{ padding: '5rem', textAlign: 'center' }}>
          <Folder size={64} color="var(--glass-border)" style={{ marginBottom: '1.5rem' }} />
          <h3 style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>暂无工程</h3>
          <p style={{ color: 'var(--text-muted)', marginBottom: '2rem' }}>开启您的第一个加工项目</p>
          <button className="btn-outline" onClick={() => setShowModal(true)}>立即创建</button>
        </div>
      ) : (
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))',
          gap: '2.5rem'
        }}>
          {projects.map((project, index) => (
            <motion.div
              key={project.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1 }}
            >
              <Link to={`/project/${project.id}`} className="glass-card hover-scale" style={{ 
                display: 'block',
                padding: '2.5rem',
                height: '100%',
                position: 'relative'
              }}>
                <div style={{ 
                  width: '50px', 
                  height: '50px', 
                  background: 'var(--glass)',
                  borderRadius: '15px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '2rem',
                  border: '1px solid var(--glass-border)'
                }}>
                  <Folder size={24} color="var(--primary)" />
                </div>

                <h3 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '1rem' }}>
                  {project.name}
                </h3>
                
                <p style={{ 
                  color: 'var(--text-muted)', 
                  marginBottom: '2.5rem',
                  height: '3rem',
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical'
                }}>
                  {project.description || '暂无描述'}
                </p>

                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'space-between', 
                  alignItems: 'center',
                  borderTop: '1px solid var(--glass-border)',
                  paddingTop: '1.5rem'
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                    <Calendar size={14} />
                    <span>{new Date(project.created_at).toLocaleDateString()}</span>
                  </div>
                  
                  <div style={{ display: 'flex', gap: '1rem' }}>
                    <button 
                      onClick={(e) => handleDelete(e, project.id)}
                      style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.3)', cursor: 'pointer', padding: '0.5rem' }}
                      className="delete-btn"
                    >
                      <Trash2 size={18} />
                    </button>
                    <div style={{ color: 'var(--primary)' }}>
                      <ArrowRight size={20} />
                    </div>
                  </div>
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}

      {/* Create Project Modal */}
      <AnimatePresence>
        {showModal && (
          <div style={{ 
            position: 'fixed', 
            inset: 0, 
            background: 'rgba(0,0,0,0.8)', 
            backdropFilter: 'blur(10px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '2rem'
          }}>
            <motion.div 
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="glass-card" 
              style={{ width: '100%', maxWidth: '500px', padding: '3rem' }}
            >
              <h2 style={{ fontSize: '2rem', marginBottom: '2rem' }}>新建工程</h2>
              <form onSubmit={handleCreate}>
                <div className="input-group">
                  <label className="input-label">工程名称</label>
                  <input 
                    type="text" 
                    className="nanfu-input" 
                    required 
                    value={newProject.name}
                    onChange={e => setNewProject({...newProject, name: e.target.value})}
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">工程描述</label>
                  <textarea 
                    className="nanfu-input" 
                    style={{ minHeight: '120px', resize: 'vertical' }}
                    value={newProject.description}
                    onChange={e => setNewProject({...newProject, description: e.target.value})}
                  />
                </div>
                <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
                  <button type="button" className="btn-outline" style={{ flex: 1 }} onClick={() => setShowModal(false)}>取消</button>
                  <button type="submit" className="btn-primary" style={{ flex: 1, justifyContent: 'center' }}>创建工程</button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <style>{`
        .delete-btn:hover {
          color: var(--primary) !important;
        }
      `}</style>
    </div>
  );
};

export default Dashboard;
