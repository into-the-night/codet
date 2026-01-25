import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import './GitHubAnalyzer.css';
import Button from './Button';
import Input from './Input';
import LoadingSpinner from './LoadingSpinner';
import StatusCard from './StatusCard';
import ProcessingStatus from './ProcessingStatus';

const GitHubAnalyzer = () => {
  const [githubUrl, setGithubUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const [analysisEvents, setAnalysisEvents] = useState([]);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [uploadMode, setUploadMode] = useState('files'); // 'files' or 'folder'
  const fileInputRef = React.useRef(null);
  const folderInputRef = React.useRef(null);
  const navigate = useNavigate();

  const validateGitHubUrl = (url) => {
    const githubRegex = /^https:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(?:\/.*)?$/;
    return githubRegex.test(url);
  };

  const handleAnalyze = async () => {
    if (!githubUrl.trim()) {
      setError('Please enter a GitHub repository URL');
      return;
    }

    if (!validateGitHubUrl(githubUrl)) {
      setError('Please enter a valid GitHub repository URL');
      return;
    }

    setError('');
    setIsAnalyzing(true);
    setAnalysisProgress(0);
    setAnalysisEvents([]);

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = process.env.REACT_APP_API_URL
      ? process.env.REACT_APP_API_URL.replace(/^https?:\/\//, '')
      : 'localhost:8000';

    const wsUrl = `${protocol}//${host}/api/ws/analyze`;
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      socket.send(JSON.stringify({ github_url: githubUrl }));
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'event') {
        setAnalysisEvents(prev => [...prev, {
          event_type: data.event_type,
          data: data.data,
          timestamp: new Date().toISOString()
        }]);

        // Update pseudo-progress based on events
        setAnalysisProgress(prev => Math.min(prev + 2, 95));
      } else if (data.type === 'info') {
        setAnalysisEvents(prev => [...prev, {
          event_type: 'info',
          data: { message: data.message },
          timestamp: new Date().toISOString()
        }]);
      } else if (data.type === 'completed') {
        setAnalysisProgress(100);
        setTimeout(() => {
          navigate(`/analysis/${data.analysis_id}`);
        }, 1000);
      } else if (data.type === 'error') {
        setError(data.message);
        setIsAnalyzing(false);
        socket.close();
      }
    };

    socket.onerror = (err) => {
      setError('Connection error. Please try again.');
      setIsAnalyzing(false);
    };

    socket.onclose = () => {
      console.log('Analysis WebSocket closed');
    };
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !isAnalyzing) {
      handleAnalyze();
    }
  };

  const handleFileUpload = (e, isFolder = false) => {
    const files = Array.from(e.target.files);
    const validFiles = files.filter(file => {
      const ext = file.name.split('.').pop().toLowerCase();
      return ['py', 'js', 'jsx', 'mjs', 'ts', 'tsx'].includes(ext);
    });

    if (validFiles.length !== files.length) {
      const skippedCount = files.length - validFiles.length;
      setError(`${skippedCount} file(s) were skipped. Only .py, .js, .jsx, .mjs, .ts, and .tsx files are allowed.`);
    } else {
      setError('');
    }

    // For folder uploads, preserve the relative paths
    if (isFolder && validFiles.length > 0) {
      const filesWithPaths = validFiles.map(file => {
        // webkitRelativePath contains the folder structure
        file.relativePath = file.webkitRelativePath || file.name;
        return file;
      });
      setUploadedFiles(filesWithPaths);
    } else {
      setUploadedFiles(validFiles);
    }

    setUploadMode(isFolder ? 'folder' : 'files');
  };

  const handleUploadAnalyze = async () => {
    if (uploadedFiles.length === 0) {
      setError('Please select files to analyze');
      return;
    }

    setError('');
    setIsAnalyzing(true);
    setAnalysisProgress(0);
    setAnalysisEvents([]); // Clear events for new analysis

    try {
      // Create FormData to upload files
      const formData = new FormData();

      // If folder upload, include relative paths
      if (uploadMode === 'folder') {
        uploadedFiles.forEach(file => {
          // Append file with its relative path as metadata
          formData.append('files', file, file.relativePath || file.name);
        });
        formData.append('preserve_structure', 'true');
      } else {
        uploadedFiles.forEach(file => {
          formData.append('files', file);
        });
      }

      // Call the backend API to upload files and get the path
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      const tempPath = response.data.path;

      // Start WebSocket analysis on the uploaded path
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = process.env.REACT_APP_API_URL
        ? process.env.REACT_APP_API_URL.replace(/^https?:\/\//, '')
        : 'localhost:8000';

      const wsUrl = `${protocol}//${host}/api/ws/analyze`;
      const socket = new WebSocket(wsUrl);

      socket.onopen = () => {
        socket.send(JSON.stringify({ path: tempPath }));
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'event') {
          setAnalysisEvents(prev => [...prev, {
            event_type: data.event_type,
            data: data.data,
            timestamp: new Date().toISOString()
          }]);
          setAnalysisProgress(prev => Math.min(prev + 2, 95));
        } else if (data.type === 'info') {
          setAnalysisEvents(prev => [...prev, {
            event_type: 'info',
            data: { message: data.message },
            timestamp: new Date().toISOString()
          }]);
        } else if (data.type === 'completed') {
          setAnalysisProgress(100);
          setTimeout(() => {
            navigate(`/analysis/${data.analysis_id}`);
          }, 1000);
        } else if (data.type === 'error') {
          setError(data.message);
          setIsAnalyzing(false);
          socket.close();
        }
      };

      socket.onerror = (err) => {
        setError('Connection error during analysis.');
        setIsAnalyzing(false);
      };
      socket.onclose = () => {
        console.log('Upload analysis WebSocket closed');
      };
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to analyze files. Please try again.');
      setIsAnalyzing(false);
      setAnalysisProgress(0);
    }
  };

  return (
    <div className="github-analyzer">
      <div className="container-sm">
        <div className="analyzer-content">
          <div className="hero-section">
            <h1 className="hero-title">
              Analyze Your
              <span className="gradient-text"> Code Quality</span>
            </h1>
            <p className="hero-description">
              Enter a GitHub repository URL to get comprehensive code quality analysis,
              security insights, and improvement recommendations.
            </p>
          </div>

          <div className="analyzer-card glass">
            <div className="card-header">
              <h2 className="card-title">Repository Analysis</h2>
              <p className="card-description">
                We'll clone your repository and analyze it for code quality, security, and best practices.
              </p>
            </div>

            <div className="input-section">
              <Input
                type="url"
                placeholder="https://github.com/username/repository"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                onKeyPress={handleKeyPress}
                disabled={isAnalyzing}
                className="github-input"
              />

              {error && (
                <div className="error-message">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                    <line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" strokeWidth="2" />
                    <line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" strokeWidth="2" />
                  </svg>
                  {error}
                </div>
              )}
            </div>

            <div className="action-section">
              <Button
                onClick={handleAnalyze}
                disabled={isAnalyzing || !githubUrl.trim()}
                className="analyze-button"
                size="large"
              >
                {isAnalyzing ? (
                  <>
                    <LoadingSpinner size="small" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M9 12L11 14L15 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <path d="M21 12C21 16.9706 16.9706 21 12 21C7.02944 21 3 16.9706 3 12C3 7.02944 7.02944 3 12 3C16.9706 3 21 7.02944 21 12Z" stroke="currentColor" strokeWidth="2" />
                    </svg>
                    Start Analysis
                  </>
                )}
              </Button>
            </div>

            <div className="divider-section">
              <div className="divider-line"></div>
              <span className="divider-text">OR</span>
              <div className="divider-line"></div>
            </div>

            <div className="upload-section">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".py,.js,.jsx,.mjs,.ts,.tsx"
                onChange={(e) => handleFileUpload(e, false)}
                style={{ display: 'none' }}
              />
              <input
                ref={folderInputRef}
                type="file"
                webkitdirectory=""
                directory=""
                multiple
                onChange={(e) => handleFileUpload(e, true)}
                style={{ display: 'none' }}
              />
              <div className="upload-buttons">
                <Button
                  variant="secondary"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isAnalyzing}
                  className="upload-button"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M21 15V19C21 20.1046 20.1046 21 19 21H5C3.89543 21 3 20.1046 3 19V15"
                      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M7 10L12 5L17 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M12 5V15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Upload Files
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => folderInputRef.current?.click()}
                  disabled={isAnalyzing}
                  className="upload-button"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M22 19C22 19.5304 21.7893 20.0391 21.4142 20.4142C21.0391 20.7893 20.5304 21 20 21H4C3.46957 21 2.96086 20.7893 2.58579 20.4142C2.21071 20.0391 2 19.5304 2 19V5C2 4.46957 2.21071 3.96086 2.58579 3.58579C2.96086 3.21071 3.46957 3 4 3H9L11 6H20C20.5304 6 21.0391 6.21071 21.4142 6.58579C21.7893 6.96086 22 7.46957 22 8V19Z"
                      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  Upload Folder
                </Button>
              </div>
              {uploadedFiles.length > 0 && (
                <div className="uploaded-files-info">
                  <p className="uploaded-count">
                    {uploadMode === 'folder'
                      ? `${uploadedFiles.length} file(s) selected from folder`
                      : `${uploadedFiles.length} file(s) selected`}
                  </p>
                  <Button
                    onClick={handleUploadAnalyze}
                    disabled={isAnalyzing}
                    className="analyze-upload-button"
                    size="medium"
                  >
                    {isAnalyzing ? (
                      <>
                        <LoadingSpinner size="small" />
                        Analyzing...
                      </>
                    ) : (
                      uploadMode === 'folder'
                        ? 'Analyze Folder'
                        : 'Analyze Files'
                    )}
                  </Button>
                </div>
              )}
            </div>

            {isAnalyzing && (
              <div className="progress-section">
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${analysisProgress}%` }}
                  />
                </div>
                <div className="progress-events">
                  <ProcessingStatus
                    events={analysisEvents}
                    isProcessing={isAnalyzing}
                    title="Analyzing Repository..."
                  />
                </div>
              </div>
            )}
          </div>

          <div className="features-section">
            <h3 className="features-title">What We Analyze</h3>
            <div className="features-grid">
              <StatusCard
                icon="🔒"
                title="Security Vulnerabilities"
                description="Detect potential security issues and vulnerabilities in your code"
              />
              <StatusCard
                icon="⚡"
                title="Performance Issues"
                description="Identify performance bottlenecks and optimization opportunities"
              />
              <StatusCard
                icon="🔄"
                title="Code Duplication"
                description="Find duplicated code blocks and suggest refactoring opportunities"
              />
              <StatusCard
                icon="📊"
                title="Complexity Analysis"
                description="Measure code complexity and maintainability metrics"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GitHubAnalyzer;
