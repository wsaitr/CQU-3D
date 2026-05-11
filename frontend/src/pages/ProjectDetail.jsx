import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
// eslint-disable-next-line no-unused-vars
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Upload, File, CheckCircle, Play, 
  RefreshCcw, Trash2, X, ChevronLeft,
  ChevronRight, Box, Image as ImageIcon,
  AlertCircle, Eye
} from 'lucide-react';
import API from '../services/api';

const ProjectDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState(null);
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [processStatus, setProcessStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  
  const fileInputRef = useRef(null);
  const statusInterval = useRef(null);

  const formatFileSize = (asset) => {
    const bytes = Number(asset.file_size ?? asset.size ?? 0);
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return '0.00 MB';
    }
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  };

  const isTaskActive = (status) => ['pending', 'processing', 'running'].includes(status);
  const isTaskCompleted = processStatus?.status === 'completed';
  const hasResult = Boolean(result) || isTaskCompleted;
  const processProgress = Math.min(Math.max(Number(processStatus?.progress ?? 0), 0), 100);
  const canStartProcess = assets.length > 0 && !isProcessing && !hasResult;

  useEffect(() => {
    fetchData();
    return () => clearInterval(statusInterval.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const fetchData = async () => {
    try {
      const pData = await API.getProject(id);
      setProject(pData);
      const aData = await API.getAssets(id);
      setAssets(aData);
      await checkProcessStatus();
      await checkResult();
    } catch (err) {
      console.error(err);
      setMessage({ type: 'error', text: err.message });
    } finally {
      setLoading(false);
    }
  };

  const checkProcessStatus = async () => {
    try {
      const status = await API.getProcessStatus(id);
      setProcessStatus(status);
      
      if (status && isTaskActive(status.status)) {
        setIsProcessing(true);
        if (!statusInterval.current) {
          statusInterval.current = setInterval(checkProcessStatus, 3000);
        }
      } else {
        setIsProcessing(false);
        if (statusInterval.current) {
          clearInterval(statusInterval.current);
          statusInterval.current = null;
          // Refresh data if just finished
          if (status?.status === 'completed') {
            fetchData();
          }
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const checkResult = async () => {
    try {
      const resultData = await API.getResult(id);
      setResult(resultData);
    } catch (err) {
      if (!err.message.includes('未找到结果')) {
        console.error(err);
      }
      setResult(null);
    }
  };

  const handleUpload = async (e) => {
    const files = e.target.files;
    if (!files.length) return;

    setIsUploading(true);
    setUploadProgress(0);
    setMessage({ type: '', text: '' });

    try {
      await API.uploadAssets(id, files, (loaded, total) => {
        setUploadProgress(Math.round((loaded / total) * 100));
      });
      setMessage({ type: 'success', text: '文件上传成功' });
      fetchData();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleProcess = async () => {
    if (hasResult) {
      setMessage({ type: 'error', text: '当前工程已有完成结果，请直接查看 PLY 模型' });
      return;
    }

    setIsProcessing(true);
    setMessage({ type: 'success', text: '任务已启动' });
    try {
      await API.triggerProcess(id);
      checkProcessStatus();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
      setIsProcessing(false);
    }
  };

  const handleDeleteAsset = async (assetId) => {
    if (!window.confirm('确定要删除这个素材吗?')) return;
    try {
      await API.deleteAsset(id, assetId);
      fetchData();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  if (loading) return <div style={{ color: 'white', textAlign: 'center', padding: '10rem' }}>加载工程详情...</div>;
  if (!project) return <div style={{ color: 'white', textAlign: 'center', padding: '10rem' }}>未找到该工程</div>;

  return (
    <div className="nanfu-container" style={{ paddingTop: '4rem', paddingBottom: '6rem' }}>
      <button 
        onClick={() => navigate('/')}
        className="btn-outline" 
        style={{ marginBottom: '2rem', padding: '0.5rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}
      >
        <ChevronLeft size={16} /> 返回控制台
      </button>

      <div style={{ marginBottom: '4rem' }}>
        <motion.h1 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          style={{ fontSize: '3rem', fontWeight: '800', marginBottom: '1rem' }}
        >
          {project.name}
        </motion.h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '1.2rem', maxWidth: '800px' }}>
          {project.description || '暂无描述'}
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '3rem' }}>
        {/* Left Column: Assets */}
        <div>
          <section className="glass-card" style={{ padding: '2.5rem', marginBottom: '3rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2.5rem' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: '700', display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
                <ImageIcon size={24} color="var(--primary)" />
                素材库 ({assets.length})
              </h2>
              <button 
                className="btn-primary" 
                onClick={() => fileInputRef.current.click()}
                disabled={isUploading}
                style={{ padding: '0.6rem 1.2rem', fontSize: '0.9rem' }}
              >
                <Upload size={18} />
                {isUploading ? '上传中...' : '上传素材'}
              </button>
              <input 
                type="file" 
                multiple 
                hidden 
                ref={fileInputRef} 
                onChange={handleUpload}
              />
            </div>

            {isUploading && (
              <div style={{ marginBottom: '2rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.9rem' }}>
                  <span>上传进度</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div style={{ height: '6px', background: 'var(--glass)', borderRadius: '100px', overflow: 'hidden' }}>
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadProgress}%` }}
                    style={{ height: '100%', background: 'var(--primary)' }}
                  />
                </div>
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {assets.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)', border: '1px dashed var(--glass-border)', borderRadius: 'var(--radius-md)' }}>
                  暂无素材，请先上传
                </div>
              ) : (
                assets.map((asset) => (
                  <motion.div 
                    layout
                    key={asset.id}
                    className="glass-card" 
                    style={{ 
                      padding: '1.2rem 1.5rem', 
                      display: 'flex', 
                      justifyContent: 'space-between', 
                      alignItems: 'center',
                      background: 'rgba(255,255,255,0.02)'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                      <div style={{ width: '40px', height: '40px', background: 'rgba(255,255,255,0.05)', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <File size={20} color="var(--text-muted)" />
                      </div>
                      <div>
                        <div style={{ fontWeight: '600', marginBottom: '0.2rem' }}>{asset.filename}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{formatFileSize(asset)}</div>
                      </div>
                    </div>
                    <button 
                      onClick={() => handleDeleteAsset(asset.id)}
                      style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.2)', cursor: 'pointer' }}
                      className="delete-btn"
                    >
                      <Trash2 size={18} />
                    </button>
                  </motion.div>
                ))
              )}
            </div>
          </section>
        </div>

        {/* Right Column: Processing */}
        <div>
          <section className="glass-card" style={{ padding: '2.5rem', position: 'sticky', top: '6rem' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '0.8rem' }}>
              <Box size={24} color="var(--primary)" />
              加工中心
            </h2>

            <div style={{ 
              background: 'rgba(0,0,0,0.3)', 
              borderRadius: 'var(--radius-md)', 
              padding: '2rem',
              textAlign: 'center',
              border: '1px solid var(--glass-border)',
              marginBottom: '2rem'
            }}>
              <div style={{ marginBottom: '1.5rem' }}>
                <div style={{ 
                  width: '80px', 
                  height: '80px', 
                  borderRadius: '100%', 
                  background: isProcessing ? 'rgba(230, 0, 8, 0.1)' : 'rgba(255,255,255,0.05)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto',
                  border: isProcessing ? '2px solid var(--primary)' : '2px solid transparent'
                }}>
                  {isProcessing ? (
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                    >
                      <RefreshCcw size={40} color="var(--primary)" />
                    </motion.div>
                  ) : (
	                <CheckCircle size={40} color={hasResult ? '#4ade80' : 'var(--text-muted)'} />
                  )}
                </div>
              </div>

              <div style={{ fontSize: '1.2rem', fontWeight: '700', marginBottom: '0.5rem' }}>
                {isProcessing ? '正在同步能量...' : (hasResult ? '加工已完成' : '准备就绪')}
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                {isProcessing ? '算法优化中，请稍后' : (hasResult ? '结果已生成，可以查看模型' : '点击下方按钮开启加工任务')}
              </p>

              {(isProcessing || processStatus) && (
                <div style={{ marginTop: '1.5rem', textAlign: 'left' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    <span>任务进度</span>
                    <span>{processProgress}%</span>
                  </div>
                  <div style={{ height: '8px', background: 'rgba(255,255,255,0.08)', borderRadius: '999px', overflow: 'hidden' }}>
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${processProgress}%` }}
                      transition={{ duration: 0.35 }}
                      style={{
                        height: '100%',
                        background: hasResult ? '#4ade80' : 'var(--primary)',
                        borderRadius: '999px'
                      }}
                    />
                  </div>
                </div>
              )}
            </div>

            <button 
              className="btn-primary" 
              style={{ width: '100%', height: '4rem', fontSize: '1.1rem', justifyContent: 'center' }}
              onClick={handleProcess}
              disabled={!canStartProcess}
            >
              <Play size={20} fill="white" />
              {hasResult ? '任务已完成' : (isProcessing ? `加工中 ${processProgress}%` : '立即开始加工')}
            </button>

            {assets.length === 0 && (
              <p style={{ color: 'var(--primary)', fontSize: '0.8rem', marginTop: '1rem', textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.4rem' }}>
                <AlertCircle size={14} /> 需要上传素材后才能开始
              </p>
            )}

            {hasResult && (
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ 
                  marginTop: '2rem', 
                  padding: '1.5rem', 
                  background: 'rgba(74, 222, 128, 0.1)', 
                  border: '1px solid #4ade80',
                  borderRadius: 'var(--radius-md)',
                  color: '#4ade80'
                }}
              >
                <div style={{ fontWeight: '700', marginBottom: '0.5rem' }}>加工结果已就绪</div>
                <button 
                  className="btn-outline" 
                  onClick={() => navigate(`/project/${id}/ply-viewer`)}
                  style={{ 
                    width: '100%', 
                    borderColor: '#4ade80', 
                    color: '#4ade80',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.6rem',
                    marginTop: '0.8rem'
                  }}
                >
                  <Eye size={16} />
                  查看 PLY 模型
                </button>
              </motion.div>
            )}
          </section>
        </div>
      </div>

      <AnimatePresence>
        {message.text && (
          <motion.div 
            initial={{ opacity: 0, y: 50 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50 }}
            style={{ 
              position: 'fixed',
              bottom: '2rem',
              left: '50%',
              transform: 'translateX(-50%)',
              padding: '1rem 2rem',
              borderRadius: '100px',
              background: message.type === 'error' ? 'var(--primary)' : '#4ade80',
              color: 'white',
              boxShadow: '0 10px 30px rgba(0,0,0,0.5)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.8rem',
              zIndex: 2000
            }}
          >
            {message.type === 'error' ? <AlertCircle size={20} /> : <CheckCircle size={20} />}
            <span>{message.text}</span>
            <button onClick={() => setMessage({type:'', text:''})} style={{ background:'none', border:'none', color:'white', cursor:'pointer', marginLeft:'1rem' }}>
              <X size={16} />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <style>{`
        .delete-btn:hover { color: var(--primary) !important; }
      `}</style>
    </div>
  );
};

export default ProjectDetail;
