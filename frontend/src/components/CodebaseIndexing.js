import React, { useState } from 'react';
import Button from './Button';
import Input from './Input';
import LoadingSpinner from './LoadingSpinner';
import Toast from './Toast';
import { indexCodebase, getIndexStatistics } from '../services/api';
import './CodebaseIndexing.css';

const CodebaseIndexing = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [path, setPath] = useState('');
  const [collectionName, setCollectionName] = useState('codebase');
  const [isIndexing, setIsIndexing] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showToast, setShowToast] = useState(false);
  const [indexStats, setIndexStats] = useState(null);

  const handleOpenModal = () => {
    setIsModalOpen(true);
    setError('');
    setSuccess('');
  };

  const handleCloseModal = () => {
    if (!isIndexing) {
      setIsModalOpen(false);
      setPath('');
      setCollectionName('codebase');
      setError('');
    }
  };

  const handleIndex = async () => {
    if (!path.trim()) {
      setError('Please enter a path to index');
      return;
    }

    setError('');
    setIsIndexing(true);

    try {
      const response = await indexCodebase(path, collectionName);
      
      setSuccess(`Successfully indexed ${response.total_chunks} code chunks!`);
      setIndexStats(response);
      setShowToast(true);
      
      // Close modal after success
      setTimeout(() => {
        setIsModalOpen(false);
        setPath('');
      }, 2000);
      
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to index codebase. Please check the path and try again.');
    } finally {
      setIsIndexing(false);
    }
  };

  const handleCheckStats = async () => {
    try {
      const stats = await getIndexStatistics(collectionName);
      setIndexStats(stats.statistics);
      setShowToast(true);
      setSuccess(`Collection "${collectionName}" contains ${stats.statistics.total_chunks} indexed chunks`);
    } catch (err) {
      setError('No indexed collection found. Please index a codebase first.');
    }
  };

  return (
    <>
      <div className="indexing-button-container">
        <Button
          onClick={handleOpenModal}
          variant="secondary"
          className="index-button"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M21 21L15 15M17 10C17 13.866 13.866 17 10 17C6.13401 17 3 13.866 3 10C3 6.13401 6.13401 3 10 3C13.866 3 17 6.13401 17 10Z" 
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Index Codebase for Search
        </Button>
      </div>

      {isModalOpen && (
        <div className="modal-overlay" onClick={handleCloseModal}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Index Codebase for Semantic Search</h2>
              <button className="close-button" onClick={handleCloseModal} disabled={isIndexing}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M6 6L18 18M6 18L18 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
            </div>

            <div className="modal-body">
              <div className="info-banner">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                  <path d="M12 16V12M12 8H12.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                <p>Currently supports <strong>Python files only</strong>. The indexer will parse functions, classes, methods, and other code constructs for intelligent search.</p>
              </div>

              <div className="form-group">
                <label htmlFor="path">Repository Path</label>
                <Input
                  id="path"
                  type="text"
                  placeholder="/path/to/your/python/project"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  disabled={isIndexing}
                />
                <small className="input-help">Enter the absolute path to your Python project directory</small>
              </div>

              <div className="form-group">
                <label htmlFor="collection">Collection Name</label>
                <Input
                  id="collection"
                  type="text"
                  placeholder="codebase"
                  value={collectionName}
                  onChange={(e) => setCollectionName(e.target.value)}
                  disabled={isIndexing}
                />
                <small className="input-help">Name for the Qdrant collection (default: codebase)</small>
              </div>

              {error && (
                <div className="error-message">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                    <line x1="15" y1="9" x2="9" y2="15" stroke="currentColor" strokeWidth="2"/>
                    <line x1="9" y1="9" x2="15" y2="15" stroke="currentColor" strokeWidth="2"/>
                  </svg>
                  {error}
                </div>
              )}

              {success && !isIndexing && (
                <div className="success-message">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M9 12L11 14L15 10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2"/>
                  </svg>
                  {success}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <Button
                variant="secondary"
                onClick={handleCheckStats}
                disabled={isIndexing}
              >
                Check Stats
              </Button>
              <Button
                onClick={handleIndex}
                disabled={isIndexing || !path.trim()}
              >
                {isIndexing ? (
                  <>
                    <LoadingSpinner size="small" />
                    Indexing...
                  </>
                ) : (
                  'Start Indexing'
                )}
              </Button>
            </div>

            {indexStats && (
              <div className="stats-section">
                <h3>Index Statistics</h3>
                <div className="stats-grid">
                  <div className="stat-item">
                    <span className="stat-label">Total Chunks</span>
                    <span className="stat-value">{indexStats.total_chunks || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Functions</span>
                    <span className="stat-value">{indexStats.type_counts?.function || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Classes</span>
                    <span className="stat-value">{indexStats.type_counts?.class || 0}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-label">Methods</span>
                    <span className="stat-value">{indexStats.type_counts?.method || 0}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {showToast && (
        <Toast
          message={success}
          type="success"
          onClose={() => setShowToast(false)}
        />
      )}
    </>
  );
};

export default CodebaseIndexing;