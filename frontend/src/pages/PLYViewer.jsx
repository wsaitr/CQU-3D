import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js';
import API from '../services/api';
import './PLYViewer.css';

const PLYViewer = () => {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const containerRef = useRef(null);
  const sceneRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState('Loading mesh...');
  const [wireframe, setWireframe] = useState(false);
  const [showSolid, setShowSolid] = useState(true);

  const loadPLYViewer = useCallback(async () => {
    try {
      if (!containerRef.current) return;

      // 清理旧的renderer
      if (sceneRef.current && sceneRef.current.renderer) {
        sceneRef.current.renderer.dispose();
        containerRef.current.innerHTML = '';
      }

      // 初始化场景
      const scene = new THREE.Scene();
      scene.background = new THREE.Color(0x181a1f);

      const camera = new THREE.PerspectiveCamera(
        55,
        containerRef.current.clientWidth / containerRef.current.clientHeight,
        0.01,
        5000
      );
      camera.position.set(2.5, 2.0, 2.5);

      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(
        containerRef.current.clientWidth,
        containerRef.current.clientHeight
      );
      containerRef.current.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;

      // 添加灯光
      scene.add(new THREE.HemisphereLight(0xffffff, 0x303744, 2.2));
      const light = new THREE.DirectionalLight(0xffffff, 1.6);
      light.position.set(4, 6, 5);
      scene.add(light);

      // 添加网格
      const grid = new THREE.GridHelper(10, 20, 0x53606f, 0x303844);
      scene.add(grid);

      let mesh;

      const fitObject = (object) => {
        const box = new THREE.Box3().setFromObject(object);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const maxSize = Math.max(size.x, size.y, size.z) || 1;
        const distance = maxSize / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));

        controls.target.copy(center);
        camera.position.copy(center).add(
          new THREE.Vector3(distance * 0.9, distance * 0.75, distance * 1.15)
        );
        camera.near = Math.max(distance / 1000, 0.001);
        camera.far = distance * 1000;
        camera.updateProjectionMatrix();
        controls.update();
      };

      const setMeshStatus = (geometry) => {
        const vertices = geometry.attributes.position?.count ?? 0;
        const faces = geometry.index ? geometry.index.count / 3 : vertices / 3;
        setStatus(
          `${vertices.toLocaleString()} vertices, ${Math.round(faces).toLocaleString()} faces`
        );
      };

      // 部署后读取当前项目结果；无登录态时保留本地 public/result.ply 预览入口。
      const token = localStorage.getItem('access_token');
      const plyUrl = token ? API.getPlyUrl(projectId) : '/result.ply';

      const loader = new PLYLoader();
      if (token) {
        loader.setRequestHeader({ Authorization: `Bearer ${token}` });
      }

      loader.load(
        plyUrl,
        (geometry) => {
          geometry.computeVertexNormals();
          const hasColor = Boolean(geometry.attributes.color);
          const material = new THREE.MeshStandardMaterial({
            color: hasColor ? 0xffffff : 0xd8dde6,
            vertexColors: hasColor,
            roughness: 0.72,
            metalness: 0.02,
            side: THREE.DoubleSide
          });
          mesh = new THREE.Mesh(geometry, material);
          scene.add(mesh);
          fitObject(mesh);
          setMeshStatus(geometry);
          setLoading(false);

          // 存储mesh引用以便后续操作
          sceneRef.current = {
            scene,
            camera,
            renderer,
            controls,
            mesh,
            fitObject
          };
        },
        undefined,
        (error) => {
          setError(`Failed to load PLY file: ${error?.message || error}`);
          setLoading(false);
          console.error('PLY loading error:', error);
        }
      );

      // 处理窗口大小变化
      const handleResize = () => {
        if (!containerRef.current) return;
        const width = containerRef.current.clientWidth;
        const height = containerRef.current.clientHeight;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
      };

      window.addEventListener('resize', handleResize);

      // 动画循环
      const animate = () => {
        requestAnimationFrame(animate);
        controls.update();
        renderer.render(scene, camera);
      };
      animate();

      // 保存场景引用
      sceneRef.current = {
        scene,
        camera,
        renderer,
        controls,
        mesh,
        fitObject
      };

      return () => {
        window.removeEventListener('resize', handleResize);
        renderer.dispose();
      };
    } catch (err) {
      setError(`Error initializing viewer: ${err.message}`);
      setLoading(false);
      console.error('Viewer initialization error:', err);
    }
  }, [projectId]);

  useEffect(() => {
    const initTimer = window.setTimeout(() => {
      loadPLYViewer();
    }, 0);
    return () => {
      window.clearTimeout(initTimer);
      if (sceneRef.current && sceneRef.current.renderer) {
        sceneRef.current.renderer.dispose();
      }
    };
  }, [loadPLYViewer]);

  const handleFit = () => {
    if (sceneRef.current && sceneRef.current.mesh) {
      sceneRef.current.fitObject(sceneRef.current.mesh);
    }
  };

  const handleWireframeToggle = (e) => {
    const newValue = e.target.checked;
    setWireframe(newValue);
    if (sceneRef.current && sceneRef.current.mesh) {
      sceneRef.current.mesh.material.wireframe = newValue;
    }
  };

  const handleSolidToggle = (e) => {
    const newValue = e.target.checked;
    setShowSolid(newValue);
    if (sceneRef.current && sceneRef.current.mesh) {
      sceneRef.current.mesh.visible = newValue;
    }
  };

  return (
    <div className="ply-viewer-container">
      <div className="ply-viewer-header">
        <button
          className="ply-back-button"
          onClick={() => navigate(-1)}
          title="返回"
        >
          <ChevronLeft size={20} />
          返回
        </button>
        <h1>PLY 模型查看器</h1>
      </div>

      {error && (
        <div className="ply-error">
          <p>{error}</p>
        </div>
      )}

      {loading && (
        <div className="ply-loading">
          <div className="spinner"></div>
          <p>正在加载模型...</p>
        </div>
      )}

      <div ref={containerRef} className="ply-viewport" />

      <div className="ply-panel">
        <div className="ply-status">{status}</div>
        <div className="ply-controls">
          <button onClick={handleFit} className="ply-button">
            适应视图
          </button>
          <label className="ply-label">
            <input
              type="checkbox"
              checked={wireframe}
              onChange={handleWireframeToggle}
            />
            网格模式
          </label>
          <label className="ply-label">
            <input
              type="checkbox"
              checked={showSolid}
              onChange={handleSolidToggle}
            />
            显示模型
          </label>
        </div>
      </div>
    </div>
  );
};

export default PLYViewer;
